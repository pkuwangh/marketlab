"""Review Bulltard candidate observations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


class CandidateReviewError(ValueError):
    """Raised when candidate observations cannot be loaded."""


@dataclass(frozen=True, slots=True)
class CandidateReview:
    """Compact review row for one Bulltard-ranked ticker."""

    source_date: date
    symbol: str
    ranked_side: str | None
    score: float | None
    trade_count: int | None
    ranked_premium: float | None
    interest_rank: int | None
    interest_note: str | None
    detail_rows: int
    latest_flow: dict[str, Any] | None
    top_flow: dict[str, Any] | None
    ticker_flow_path: Path


def load_candidate_reviews(
    *,
    source_date: date,
    observations_root: Path,
    limit: int,
) -> tuple[CandidateReview, ...]:
    """Load ranked candidates and attach ticker-flow details when present."""

    ranked_path = observations_root / "ranked_option_trades" / f"{source_date.isoformat()}.jsonl"
    interest_path = observations_root / "trades_of_interest" / f"{source_date.isoformat()}.jsonl"

    ranked_rows = tuple(_read_jsonl(ranked_path)) if ranked_path.is_file() else ()
    interest_rows = tuple(_read_jsonl(interest_path)) if interest_path.is_file() else ()
    if not ranked_rows and not interest_rows:
        raise CandidateReviewError(
            f"No candidate observations found: {ranked_path} or {interest_path}"
        )

    interest_by_symbol = {str(row["symbol"]).upper(): row for row in interest_rows}
    reviews = []
    for ranked_row in ranked_rows:
        symbol = str(ranked_row["symbol"]).upper()
        reviews.append(
            _review_from_observation_rows(
                source_date=source_date,
                observations_root=observations_root,
                ranked_row=ranked_row,
                interest_row=interest_by_symbol.pop(symbol, None),
            )
        )
    for interest_row in sorted(interest_by_symbol.values(), key=lambda row: int(row["rank"])):
        reviews.append(
            _review_from_observation_rows(
                source_date=source_date,
                observations_root=observations_root,
                ranked_row=None,
                interest_row=interest_row,
            )
        )

    reviews.sort(key=_review_sort_key)
    return tuple(reviews[:limit])


def format_candidate_reviews(reviews: tuple[CandidateReview, ...]) -> str:
    """Format candidate reviews as a compact plain-text table."""

    if not reviews:
        return "No candidates found."

    rows = [
        [
            "symbol",
            "source",
            "side",
            "score",
            "trades",
            "premium",
            "detail",
            "interest_note",
            "latest_flow",
            "top_flow",
        ]
    ]
    for review in reviews:
        rows.append(
            [
                review.symbol,
                _format_source(review),
                review.ranked_side or "-",
                f"{review.score:g}" if review.score is not None else "-",
                str(review.trade_count) if review.trade_count is not None else "-",
                format_money(review.ranked_premium) if review.ranked_premium is not None else "-",
                str(review.detail_rows),
                _format_interest_note(review),
                _format_flow(review.latest_flow, include_time=True),
                _format_flow(review.top_flow, include_time=False),
            ]
        )

    return _format_table(rows)


def format_money(value: float) -> str:
    """Format a dollar value compactly for terminal tables."""

    absolute = abs(value)
    for suffix, scale in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if absolute >= scale:
            scaled = value / scale
            precision = 0 if abs(scaled) >= 100 else 1
            return f"${scaled:.{precision}f}{suffix}"
    return f"${value:.0f}"


def _review_from_observation_rows(
    *,
    source_date: date,
    observations_root: Path,
    ranked_row: dict[str, Any] | None,
    interest_row: dict[str, Any] | None,
) -> CandidateReview:
    if ranked_row is None and interest_row is None:
        raise CandidateReviewError("Candidate review requires at least one observation row")

    source_row = ranked_row if ranked_row is not None else interest_row
    if source_row is None:
        raise CandidateReviewError("Candidate review requires at least one observation row")
    symbol = str(source_row["symbol"]).upper()
    ticker_flow_path = (
        observations_root / "ticker_flow" / symbol / f"{source_date.isoformat()}.jsonl"
    )
    flow_rows = tuple(_read_jsonl(ticker_flow_path)) if ticker_flow_path.is_file() else ()
    latest_flow = max(flow_rows, key=lambda flow: str(flow.get("traded_at", "")), default=None)
    top_flow = max(flow_rows, key=lambda flow: float(flow.get("premium") or 0.0), default=None)

    return CandidateReview(
        source_date=source_date,
        symbol=symbol,
        ranked_side=str(ranked_row["side"]) if ranked_row is not None else None,
        score=float(ranked_row["score"]) if ranked_row is not None else None,
        trade_count=int(ranked_row["trade_count"]) if ranked_row is not None else None,
        ranked_premium=float(ranked_row["premium"]) if ranked_row is not None else None,
        interest_rank=int(interest_row["rank"]) if interest_row is not None else None,
        interest_note=str(interest_row["note"]) if interest_row is not None else None,
        detail_rows=len(flow_rows),
        latest_flow=latest_flow,
        top_flow=top_flow,
        ticker_flow_path=ticker_flow_path,
    )


def _review_sort_key(review: CandidateReview) -> tuple[int, float, float, int, str]:
    if review.score is not None:
        return (
            0,
            -abs(review.score),
            -(review.ranked_premium or 0.0),
            review.interest_rank or 9999,
            review.symbol,
        )
    return (1, 0.0, 0.0, review.interest_rank or 9999, review.symbol)


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    try:
        return tuple(
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError as exc:
        raise CandidateReviewError(f"Failed to read observations file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CandidateReviewError(f"Invalid JSONL observations file: {path}") from exc


def _format_flow(flow: dict[str, Any] | None, *, include_time: bool) -> str:
    if flow is None:
        return "-"

    parts = [
        str(flow.get("order_type", "")),
        str(flow.get("contract", "")),
        str(flow.get("expiry", "")),
        format_money(float(flow.get("premium") or 0.0)),
    ]
    if include_time:
        parts.insert(0, str(flow.get("traded_at", "")).replace("T", " "))
    return " ".join(part for part in parts if part)


def _format_source(review: CandidateReview) -> str:
    if review.score is not None and review.interest_rank is not None:
        return f"ranked+interest#{review.interest_rank}"
    if review.score is not None:
        return "ranked"
    return f"interest#{review.interest_rank}" if review.interest_rank is not None else "-"


def _format_interest_note(review: CandidateReview) -> str:
    if not review.interest_note:
        return "-"
    return _clip(review.interest_note, 90)


def _clip(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def _format_table(rows: list[list[str]]) -> str:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    lines = []
    for row_index, row in enumerate(rows):
        lines.append("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)
