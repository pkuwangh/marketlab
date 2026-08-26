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
    side: str
    score: float
    trade_count: int
    ranked_premium: float
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
    if not ranked_path.is_file():
        raise CandidateReviewError(f"Ranked observations not found: {ranked_path}")

    ranked_rows = tuple(_read_jsonl(ranked_path))
    if not ranked_rows:
        raise CandidateReviewError(f"Ranked observations file is empty: {ranked_path}")

    reviews = [_review_from_ranked_row(row, source_date, observations_root) for row in ranked_rows]
    reviews.sort(
        key=lambda review: (
            abs(review.score),
            review.ranked_premium,
            review.trade_count,
            review.symbol,
        ),
        reverse=True,
    )
    return tuple(reviews[:limit])


def format_candidate_reviews(reviews: tuple[CandidateReview, ...]) -> str:
    """Format candidate reviews as a compact plain-text table."""

    if not reviews:
        return "No candidates found."

    rows = [
        [
            "symbol",
            "side",
            "score",
            "trades",
            "premium",
            "detail",
            "latest_flow",
            "top_flow",
        ]
    ]
    for review in reviews:
        rows.append(
            [
                review.symbol,
                review.side,
                f"{review.score:g}",
                str(review.trade_count),
                format_money(review.ranked_premium),
                str(review.detail_rows),
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


def _review_from_ranked_row(
    row: dict[str, Any],
    source_date: date,
    observations_root: Path,
) -> CandidateReview:
    symbol = str(row["symbol"]).upper()
    ticker_flow_path = (
        observations_root / "ticker_flow" / symbol / f"{source_date.isoformat()}.jsonl"
    )
    flow_rows = tuple(_read_jsonl(ticker_flow_path)) if ticker_flow_path.is_file() else ()
    latest_flow = max(flow_rows, key=lambda flow: str(flow.get("traded_at", "")), default=None)
    top_flow = max(flow_rows, key=lambda flow: float(flow.get("premium") or 0.0), default=None)

    return CandidateReview(
        source_date=source_date,
        symbol=symbol,
        side=str(row["side"]),
        score=float(row["score"]),
        trade_count=int(row["trade_count"]),
        ranked_premium=float(row["premium"]),
        detail_rows=len(flow_rows),
        latest_flow=latest_flow,
        top_flow=top_flow,
        ticker_flow_path=ticker_flow_path,
    )


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


def _format_table(rows: list[list[str]]) -> str:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    lines = []
    for row_index, row in enumerate(rows):
        lines.append("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)
