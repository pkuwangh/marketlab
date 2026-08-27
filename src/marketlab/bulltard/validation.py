"""Bulltard candidate validation against independent price observations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger

from marketlab.bulltard.candidates import (
    CandidateReview,
    CandidateReviewError,
    format_money,
    load_candidate_reviews,
)
from marketlab.bulltard.ingest import DEFAULT_OBSERVATIONS_ROOT
from marketlab.prices import (
    DEFAULT_PRICE_OBSERVATIONS_ROOT,
    DailyPriceObservation,
    PriceDataError,
    load_price_history,
)

DEFAULT_CANDIDATE_SNAPSHOT_ROOT = Path("data/snapshots/bulltard/candidates")
FEATURE_VERSION = "bulltard_candidate_validation_v0"
DEFAULT_MIN_DOLLAR_VOLUME = 50_000_000.0
BENCHMARK_SYMBOLS = ("SPY", "QQQ")


class CandidateValidationError(ValueError):
    """Raised when Bulltard candidate validation cannot run."""


@dataclass(frozen=True, slots=True)
class CandidateValidationSnapshot:
    """Point-in-time validation row for one Bulltard candidate."""

    source_date: date
    feature_version: str
    symbol: str
    bulltard_source: str
    ranked_side: str | None
    ranked_score: float | None
    ranked_trade_count: int | None
    ranked_premium: float | None
    interest_rank: int | None
    detail_rows: int
    price_date: date | None
    close: float | None
    dollar_volume: float | None
    return_5d: float | None
    return_20d: float | None
    return_60d: float | None
    ma20_distance: float | None
    ma50_distance: float | None
    ma200_distance: float | None
    drawdown_60d: float | None
    relative_strength_20d_spy: float | None
    relative_strength_20d_qqq: float | None
    underlying_liquidity_status: str
    options_liquidity_status: str
    validation_status: str
    validation_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": "marketlab",
            "snapshot_type": "bulltard-candidate-validation",
            "source_date": self.source_date.isoformat(),
            "feature_version": self.feature_version,
            "symbol": self.symbol,
            "bulltard_source": self.bulltard_source,
            "ranked_side": self.ranked_side,
            "ranked_score": self.ranked_score,
            "ranked_trade_count": self.ranked_trade_count,
            "ranked_premium": self.ranked_premium,
            "interest_rank": self.interest_rank,
            "detail_rows": self.detail_rows,
            "price_date": self.price_date.isoformat() if self.price_date else None,
            "close": self.close,
            "dollar_volume": self.dollar_volume,
            "return_5d": self.return_5d,
            "return_20d": self.return_20d,
            "return_60d": self.return_60d,
            "ma20_distance": self.ma20_distance,
            "ma50_distance": self.ma50_distance,
            "ma200_distance": self.ma200_distance,
            "drawdown_60d": self.drawdown_60d,
            "relative_strength_20d_spy": self.relative_strength_20d_spy,
            "relative_strength_20d_qqq": self.relative_strength_20d_qqq,
            "underlying_liquidity_status": self.underlying_liquidity_status,
            "options_liquidity_status": self.options_liquidity_status,
            "validation_status": self.validation_status,
            "validation_reasons": list(self.validation_reasons),
        }


@dataclass(frozen=True, slots=True)
class CandidateValidationResult:
    """Result of one candidate validation run."""

    source_date: date
    snapshots: tuple[CandidateValidationSnapshot, ...]
    snapshot_path: Path | None
    table: str


@dataclass(frozen=True, slots=True)
class _PriceFeatures:
    price_date: date | None
    close: float | None
    dollar_volume: float | None
    return_5d: float | None
    return_20d: float | None
    return_60d: float | None
    ma20_distance: float | None
    ma50_distance: float | None
    ma200_distance: float | None
    drawdown_60d: float | None
    relative_strength_20d_spy: float | None
    relative_strength_20d_qqq: float | None


def validate_bulltard_candidates(
    *,
    source_date: date,
    observations_root: Path = DEFAULT_OBSERVATIONS_ROOT,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    snapshot_root: Path = DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
    limit: int = 12,
    min_dollar_volume: float = DEFAULT_MIN_DOLLAR_VOLUME,
    write_snapshot: bool = True,
) -> CandidateValidationResult:
    """Validate Bulltard candidates with point-in-time price features."""

    try:
        reviews = load_candidate_reviews(
            source_date=source_date,
            observations_root=observations_root,
            limit=limit,
        )
    except CandidateReviewError as exc:
        raise CandidateValidationError(str(exc)) from exc

    histories = _load_price_histories(
        symbols=tuple(review.symbol for review in reviews) + BENCHMARK_SYMBOLS,
        price_root=price_root,
    )
    snapshots = tuple(
        _validate_review(
            review=review,
            histories=histories,
            min_dollar_volume=min_dollar_volume,
        )
        for review in reviews
    )
    snapshot_path = (
        write_candidate_validation_snapshots(
            snapshots,
            snapshot_root=snapshot_root,
            source_date=source_date,
        )
        if write_snapshot
        else None
    )
    table = format_candidate_validation_snapshots(snapshots)
    logger.bind(
        source_date=source_date.isoformat(),
        candidate_count=len(snapshots),
        snapshot_path=str(snapshot_path) if snapshot_path else None,
    ).success("Validated Bulltard candidates")
    return CandidateValidationResult(
        source_date=source_date,
        snapshots=snapshots,
        snapshot_path=snapshot_path,
        table=table,
    )


def write_candidate_validation_snapshots(
    snapshots: tuple[CandidateValidationSnapshot, ...],
    *,
    snapshot_root: Path = DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
    source_date: date,
) -> Path:
    """Write one date's candidate validation snapshots."""

    path = snapshot_root / f"{source_date.isoformat()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(snapshot.to_dict(), sort_keys=True) + "\n" for snapshot in snapshots
    )
    path.write_text(payload, encoding="utf-8")
    logger.bind(
        source_date=source_date.isoformat(),
        row_count=len(snapshots),
        snapshot_path=str(path),
    ).success("Wrote Bulltard candidate validation snapshots")
    return path


def load_candidate_validation_snapshots(
    *,
    source_date: date,
    snapshot_root: Path = DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
) -> tuple[CandidateValidationSnapshot, ...]:
    """Load one date's candidate validation snapshots."""

    path = snapshot_root / f"{source_date.isoformat()}.jsonl"
    if not path.is_file():
        return ()
    try:
        return tuple(
            _snapshot_from_dict(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError as exc:
        raise CandidateValidationError(f"Failed to read candidate snapshots: {path}") from exc
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise CandidateValidationError(f"Invalid candidate snapshot file: {path}") from exc


def format_candidate_validation_snapshots(
    snapshots: tuple[CandidateValidationSnapshot, ...],
) -> str:
    """Format candidate validation snapshots as a compact table."""

    if not snapshots:
        return "No validated candidates found."

    rows = [
        [
            "symbol",
            "source",
            "status",
            "close",
            "dollar_vol",
            "ret20",
            "rs_spy20",
            "ma50",
            "dd60",
            "opt_liq",
            "reason",
        ]
    ]
    for snapshot in snapshots:
        rows.append(
            [
                snapshot.symbol,
                snapshot.bulltard_source,
                snapshot.validation_status,
                _format_optional_float(snapshot.close),
                format_money(snapshot.dollar_volume) if snapshot.dollar_volume is not None else "-",
                _format_percent(snapshot.return_20d),
                _format_percent(snapshot.relative_strength_20d_spy),
                _format_percent(snapshot.ma50_distance),
                _format_percent(snapshot.drawdown_60d),
                snapshot.options_liquidity_status,
                ",".join(snapshot.validation_reasons),
            ]
        )
    return _format_table(rows)


def _validate_review(
    *,
    review: CandidateReview,
    histories: dict[str, tuple[DailyPriceObservation, ...]],
    min_dollar_volume: float,
) -> CandidateValidationSnapshot:
    features = _price_features(
        symbol=review.symbol,
        source_date=review.source_date,
        histories=histories,
    )
    underlying_status = _underlying_liquidity_status(
        features=features,
        min_dollar_volume=min_dollar_volume,
    )
    validation_status, validation_reasons = _validation_status(
        features=features,
        underlying_liquidity_status=underlying_status,
    )
    return CandidateValidationSnapshot(
        source_date=review.source_date,
        feature_version=FEATURE_VERSION,
        symbol=review.symbol,
        bulltard_source=_review_source(review),
        ranked_side=review.ranked_side,
        ranked_score=review.score,
        ranked_trade_count=review.trade_count,
        ranked_premium=review.ranked_premium,
        interest_rank=review.interest_rank,
        detail_rows=review.detail_rows,
        price_date=features.price_date,
        close=features.close,
        dollar_volume=features.dollar_volume,
        return_5d=features.return_5d,
        return_20d=features.return_20d,
        return_60d=features.return_60d,
        ma20_distance=features.ma20_distance,
        ma50_distance=features.ma50_distance,
        ma200_distance=features.ma200_distance,
        drawdown_60d=features.drawdown_60d,
        relative_strength_20d_spy=features.relative_strength_20d_spy,
        relative_strength_20d_qqq=features.relative_strength_20d_qqq,
        underlying_liquidity_status=underlying_status,
        options_liquidity_status="unknown",
        validation_status=validation_status,
        validation_reasons=validation_reasons,
    )


def _load_price_histories(
    *,
    symbols: tuple[str, ...],
    price_root: Path,
) -> dict[str, tuple[DailyPriceObservation, ...]]:
    histories: dict[str, tuple[DailyPriceObservation, ...]] = {}
    for symbol in symbols:
        try:
            histories[symbol.upper()] = load_price_history(symbol=symbol, price_root=price_root)
        except PriceDataError as exc:
            raise CandidateValidationError(str(exc)) from exc
    return histories


def _price_features(
    *,
    symbol: str,
    source_date: date,
    histories: dict[str, tuple[DailyPriceObservation, ...]],
) -> _PriceFeatures:
    history = histories.get(symbol, ())
    index = _asof_index(history, source_date)
    if index is None:
        return _empty_price_features()

    current = history[index]
    return_5d = _lookback_return(history, index=index, lookback=5)
    return_20d = _lookback_return(history, index=index, lookback=20)
    return _PriceFeatures(
        price_date=current.observed_date,
        close=current.close,
        dollar_volume=current.dollar_volume,
        return_5d=return_5d,
        return_20d=return_20d,
        return_60d=_lookback_return(history, index=index, lookback=60),
        ma20_distance=_moving_average_distance(history, index=index, window=20),
        ma50_distance=_moving_average_distance(history, index=index, window=50),
        ma200_distance=_moving_average_distance(history, index=index, window=200),
        drawdown_60d=_drawdown_from_high(history, index=index, window=60),
        relative_strength_20d_spy=_relative_strength(
            return_value=return_20d,
            benchmark_history=histories.get("SPY", ()),
            source_date=source_date,
            lookback=20,
        ),
        relative_strength_20d_qqq=_relative_strength(
            return_value=return_20d,
            benchmark_history=histories.get("QQQ", ()),
            source_date=source_date,
            lookback=20,
        ),
    )


def _empty_price_features() -> _PriceFeatures:
    return _PriceFeatures(
        price_date=None,
        close=None,
        dollar_volume=None,
        return_5d=None,
        return_20d=None,
        return_60d=None,
        ma20_distance=None,
        ma50_distance=None,
        ma200_distance=None,
        drawdown_60d=None,
        relative_strength_20d_spy=None,
        relative_strength_20d_qqq=None,
    )


def _asof_index(history: tuple[DailyPriceObservation, ...], source_date: date) -> int | None:
    for index in range(len(history) - 1, -1, -1):
        if history[index].observed_date <= source_date:
            return index
    return None


def _lookback_return(
    history: tuple[DailyPriceObservation, ...],
    *,
    index: int,
    lookback: int,
) -> float | None:
    past_index = index - lookback
    if past_index < 0:
        return None
    past_close = history[past_index].close
    if past_close == 0:
        return None
    return history[index].close / past_close - 1.0


def _moving_average_distance(
    history: tuple[DailyPriceObservation, ...],
    *,
    index: int,
    window: int,
) -> float | None:
    start = index - window + 1
    if start < 0:
        return None
    closes = [row.close for row in history[start : index + 1]]
    average = sum(closes) / len(closes)
    if average == 0:
        return None
    return history[index].close / average - 1.0


def _drawdown_from_high(
    history: tuple[DailyPriceObservation, ...],
    *,
    index: int,
    window: int,
) -> float | None:
    start = max(0, index - window + 1)
    high = max(row.high for row in history[start : index + 1])
    if high == 0:
        return None
    return history[index].close / high - 1.0


def _relative_strength(
    *,
    return_value: float | None,
    benchmark_history: tuple[DailyPriceObservation, ...],
    source_date: date,
    lookback: int,
) -> float | None:
    if return_value is None:
        return None
    benchmark_index = _asof_index(benchmark_history, source_date)
    if benchmark_index is None:
        return None
    benchmark_return = _lookback_return(
        benchmark_history,
        index=benchmark_index,
        lookback=lookback,
    )
    if benchmark_return is None:
        return None
    return return_value - benchmark_return


def _underlying_liquidity_status(
    *,
    features: _PriceFeatures,
    min_dollar_volume: float,
) -> str:
    if features.dollar_volume is None:
        return "missing"
    if features.dollar_volume < min_dollar_volume:
        return "thin"
    return "liquid"


def _validation_status(
    *,
    features: _PriceFeatures,
    underlying_liquidity_status: str,
) -> tuple[str, tuple[str, ...]]:
    if features.close is None:
        return "avoid", ("missing_price_history",)
    if underlying_liquidity_status == "thin":
        return "avoid", ("thin_underlying",)
    if (
        features.return_20d is None
        or features.ma50_distance is None
        or features.relative_strength_20d_spy is None
    ):
        return "watch", ("insufficient_history",)

    reasons = []
    if features.return_20d > 0:
        reasons.append("positive_20d")
    if features.relative_strength_20d_spy > 0:
        reasons.append("rs_spy_positive")
    if features.relative_strength_20d_qqq is not None and features.relative_strength_20d_qqq >= 0:
        reasons.append("rs_qqq_positive")
    if features.ma50_distance > 0:
        reasons.append("above_ma50")
    if features.drawdown_60d is not None and features.drawdown_60d > -0.15:
        reasons.append("controlled_drawdown")

    if {"positive_20d", "rs_spy_positive", "above_ma50"}.issubset(reasons):
        return "confirm", tuple(reasons)

    if (
        features.return_20d < -0.05
        and features.relative_strength_20d_spy < -0.05
        and features.ma50_distance < -0.05
    ):
        return "avoid", ("weak_trend", "negative_relative_strength", "below_ma50")

    return "watch", tuple(reasons or ("mixed_price_action",))


def _review_source(review: CandidateReview) -> str:
    if review.score is not None and review.interest_rank is not None:
        return f"ranked+interest#{review.interest_rank}"
    if review.score is not None:
        return "ranked"
    return f"interest#{review.interest_rank}" if review.interest_rank is not None else "-"


def _snapshot_from_dict(row: dict[str, Any]) -> CandidateValidationSnapshot:
    return CandidateValidationSnapshot(
        source_date=date.fromisoformat(str(row["source_date"])),
        feature_version=str(row["feature_version"]),
        symbol=str(row["symbol"]),
        bulltard_source=str(row["bulltard_source"]),
        ranked_side=str(row["ranked_side"]) if row["ranked_side"] is not None else None,
        ranked_score=_optional_float(row["ranked_score"]),
        ranked_trade_count=_optional_int(row["ranked_trade_count"]),
        ranked_premium=_optional_float(row["ranked_premium"]),
        interest_rank=_optional_int(row["interest_rank"]),
        detail_rows=int(row["detail_rows"]),
        price_date=date.fromisoformat(str(row["price_date"])) if row["price_date"] else None,
        close=_optional_float(row["close"]),
        dollar_volume=_optional_float(row["dollar_volume"]),
        return_5d=_optional_float(row["return_5d"]),
        return_20d=_optional_float(row["return_20d"]),
        return_60d=_optional_float(row["return_60d"]),
        ma20_distance=_optional_float(row["ma20_distance"]),
        ma50_distance=_optional_float(row["ma50_distance"]),
        ma200_distance=_optional_float(row["ma200_distance"]),
        drawdown_60d=_optional_float(row["drawdown_60d"]),
        relative_strength_20d_spy=_optional_float(row["relative_strength_20d_spy"]),
        relative_strength_20d_qqq=_optional_float(row["relative_strength_20d_qqq"]),
        underlying_liquidity_status=str(row["underlying_liquidity_status"]),
        options_liquidity_status=str(row["options_liquidity_status"]),
        validation_status=str(row["validation_status"]),
        validation_reasons=tuple(str(reason) for reason in row["validation_reasons"]),
    )


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:+.1f}%"


def _format_table(rows: list[list[str]]) -> str:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    lines = []
    for row_index, row in enumerate(rows):
        lines.append("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)
