"""Forward outcome replay for Bulltard candidate validation snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from loguru import logger

from marketlab.bulltard.validation import (
    DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
    CandidateValidationError,
    CandidateValidationSnapshot,
    load_candidate_validation_snapshots,
)
from marketlab.prices import (
    DEFAULT_PRICE_OBSERVATIONS_ROOT,
    DailyPriceObservation,
    PriceDataError,
    load_price_history,
)

DEFAULT_OUTCOME_HORIZONS = (20, 40, 65, 126)


class CandidateOutcomeError(ValueError):
    """Raised when Bulltard candidate outcomes cannot be computed."""


@dataclass(frozen=True, slots=True)
class ForwardOutcome:
    """One forward outcome for one candidate and horizon."""

    source_date: date
    symbol: str
    bulltard_source: str
    source_bucket: str
    validation_status: str
    detail_bucket: str
    horizon_days: int
    return_value: float | None
    relative_strength_spy: float | None
    max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class OutcomeSummaryRow:
    """Aggregate forward outcome row for one cohort and horizon."""

    cohort: str
    horizon_days: int
    candidate_count: int
    available_count: int
    avg_return: float | None
    hit_rate: float | None
    avg_relative_strength_spy: float | None
    avg_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class CandidateOutcomeResult:
    """Result of one Bulltard outcome replay."""

    start_date: date
    end_date: date
    outcomes: tuple[ForwardOutcome, ...]
    summary_rows: tuple[OutcomeSummaryRow, ...]
    table: str


def compute_bulltard_outcomes(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path = DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    horizons: tuple[int, ...] = DEFAULT_OUTCOME_HORIZONS,
) -> CandidateOutcomeResult:
    """Compute forward outcomes for saved Bulltard candidate snapshots."""

    if end_date < start_date:
        raise CandidateOutcomeError("End date must be on or after start date")

    snapshots = _load_snapshots_in_range(
        start_date=start_date,
        end_date=end_date,
        snapshot_root=snapshot_root,
    )
    if not snapshots:
        raise CandidateOutcomeError(
            f"No candidate validation snapshots found from {start_date} to {end_date}"
        )

    histories = _load_histories(
        symbols=tuple({snapshot.symbol for snapshot in snapshots} | {"SPY"}),
        price_root=price_root,
    )
    outcomes = tuple(
        outcome
        for snapshot in snapshots
        for outcome in _snapshot_outcomes(
            snapshot=snapshot,
            histories=histories,
            horizons=horizons,
        )
    )
    summary_rows = summarize_outcomes(outcomes)
    table = format_outcome_summary(summary_rows)
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        snapshot_count=len(snapshots),
        outcome_count=len(outcomes),
    ).success("Computed Bulltard candidate outcomes")
    return CandidateOutcomeResult(
        start_date=start_date,
        end_date=end_date,
        outcomes=outcomes,
        summary_rows=summary_rows,
        table=table,
    )


def summarize_outcomes(outcomes: tuple[ForwardOutcome, ...]) -> tuple[OutcomeSummaryRow, ...]:
    """Summarize forward outcomes by useful Bulltard cohorts."""

    cohort_members: dict[str, set[ForwardOutcome]] = {}
    for outcome in outcomes:
        for cohort in _cohorts(outcome):
            cohort_members.setdefault(cohort, set()).add(outcome)

    rows: list[OutcomeSummaryRow] = []
    for cohort in sorted(cohort_members):
        cohort_outcomes = tuple(cohort_members[cohort])
        for horizon in sorted({outcome.horizon_days for outcome in cohort_outcomes}):
            horizon_outcomes = tuple(
                outcome for outcome in cohort_outcomes if outcome.horizon_days == horizon
            )
            available = tuple(
                outcome for outcome in horizon_outcomes if outcome.return_value is not None
            )
            rows.append(
                OutcomeSummaryRow(
                    cohort=cohort,
                    horizon_days=horizon,
                    candidate_count=len(horizon_outcomes),
                    available_count=len(available),
                    avg_return=_average(outcome.return_value for outcome in available),
                    hit_rate=_average(
                        1.0
                        if outcome.return_value is not None and outcome.return_value > 0
                        else 0.0
                        for outcome in available
                    ),
                    avg_relative_strength_spy=_average(
                        outcome.relative_strength_spy for outcome in available
                    ),
                    avg_max_drawdown=_average(outcome.max_drawdown for outcome in available),
                )
            )
    return tuple(rows)


def format_outcome_summary(rows: tuple[OutcomeSummaryRow, ...]) -> str:
    """Format outcome summaries as a compact table."""

    if not rows:
        return "No outcome rows found."

    table = [
        [
            "cohort",
            "horizon",
            "candidates",
            "available",
            "avg_return",
            "hit_rate",
            "avg_rs_spy",
            "avg_drawdown",
        ]
    ]
    for row in rows:
        table.append(
            [
                row.cohort,
                f"{row.horizon_days}d",
                str(row.candidate_count),
                str(row.available_count),
                _format_percent(row.avg_return),
                _format_percent(row.hit_rate),
                _format_percent(row.avg_relative_strength_spy),
                _format_percent(row.avg_max_drawdown),
            ]
        )
    return _format_table(table)


def _load_snapshots_in_range(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path,
) -> tuple[CandidateValidationSnapshot, ...]:
    snapshots: list[CandidateValidationSnapshot] = []
    for path in sorted(snapshot_root.glob("*.jsonl")):
        try:
            source_date = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if start_date <= source_date <= end_date:
            try:
                snapshots.extend(
                    load_candidate_validation_snapshots(
                        source_date=source_date,
                        snapshot_root=snapshot_root,
                    )
                )
            except CandidateValidationError as exc:
                raise CandidateOutcomeError(str(exc)) from exc
    return tuple(snapshots)


def _load_histories(
    *,
    symbols: tuple[str, ...],
    price_root: Path,
) -> dict[str, tuple[DailyPriceObservation, ...]]:
    histories: dict[str, tuple[DailyPriceObservation, ...]] = {}
    for symbol in symbols:
        try:
            histories[symbol] = load_price_history(symbol=symbol, price_root=price_root)
        except PriceDataError as exc:
            raise CandidateOutcomeError(str(exc)) from exc
    return histories


def _snapshot_outcomes(
    *,
    snapshot: CandidateValidationSnapshot,
    histories: dict[str, tuple[DailyPriceObservation, ...]],
    horizons: tuple[int, ...],
) -> tuple[ForwardOutcome, ...]:
    history = histories.get(snapshot.symbol, ())
    spy_history = histories.get("SPY", ())
    index = _exact_date_index(history, snapshot.price_date) if snapshot.price_date else None
    spy_index = _exact_date_index(spy_history, snapshot.price_date) if snapshot.price_date else None
    return tuple(
        _forward_outcome(
            snapshot=snapshot,
            history=history,
            index=index,
            spy_history=spy_history,
            spy_index=spy_index,
            horizon=horizon,
        )
        for horizon in horizons
    )


def _forward_outcome(
    *,
    snapshot: CandidateValidationSnapshot,
    history: tuple[DailyPriceObservation, ...],
    index: int | None,
    spy_history: tuple[DailyPriceObservation, ...],
    spy_index: int | None,
    horizon: int,
) -> ForwardOutcome:
    return_value = _forward_return(history, index=index, horizon=horizon)
    spy_return = _forward_return(spy_history, index=spy_index, horizon=horizon)
    relative_strength_spy = (
        return_value - spy_return if return_value is not None and spy_return is not None else None
    )
    return ForwardOutcome(
        source_date=snapshot.source_date,
        symbol=snapshot.symbol,
        bulltard_source=snapshot.bulltard_source,
        source_bucket=_source_bucket(snapshot),
        validation_status=snapshot.validation_status,
        detail_bucket="with_detail" if snapshot.detail_rows > 0 else "no_detail",
        horizon_days=horizon,
        return_value=return_value,
        relative_strength_spy=relative_strength_spy,
        max_drawdown=_forward_max_drawdown(history, index=index, horizon=horizon),
    )


def _exact_date_index(
    history: tuple[DailyPriceObservation, ...],
    observed_date: date,
) -> int | None:
    for index, row in enumerate(history):
        if row.observed_date == observed_date:
            return index
    return None


def _forward_return(
    history: tuple[DailyPriceObservation, ...],
    *,
    index: int | None,
    horizon: int,
) -> float | None:
    if index is None:
        return None
    future_index = index + horizon
    if future_index >= len(history):
        return None
    current_close = history[index].return_close
    if current_close == 0:
        return None
    return history[future_index].return_close / current_close - 1.0


def _forward_max_drawdown(
    history: tuple[DailyPriceObservation, ...],
    *,
    index: int | None,
    horizon: int,
) -> float | None:
    if index is None:
        return None
    future_index = index + horizon
    if future_index >= len(history):
        return None
    current_close = history[index].return_close
    if current_close == 0:
        return None
    lows = [row.return_close for row in history[index + 1 : future_index + 1]]
    if not lows:
        return None
    return min(lows) / current_close - 1.0


def _source_bucket(snapshot: CandidateValidationSnapshot) -> str:
    if snapshot.interest_rank is not None and snapshot.ranked_score is not None:
        return "ranked+interest"
    if snapshot.interest_rank is not None:
        return "interest"
    return "ranked"


def _cohorts(outcome: ForwardOutcome) -> tuple[str, ...]:
    return (
        "all",
        f"source:{outcome.source_bucket}",
        f"status:{outcome.validation_status}",
        f"detail:{outcome.detail_bucket}",
    )


def _average(values) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


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
