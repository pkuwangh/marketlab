from datetime import date, timedelta
from pathlib import Path

from marketlab.bulltard.outcomes import compute_bulltard_outcomes
from marketlab.bulltard.validation import (
    CandidateValidationSnapshot,
    write_candidate_validation_snapshots,
)
from marketlab.prices import DailyPriceObservation, write_price_observations


def test_compute_bulltard_outcomes_summarizes_candidate_cohorts(tmp_path: Path) -> None:
    source_date = date(2026, 1, 1)
    snapshot_root = tmp_path / "snapshots"
    price_root = tmp_path / "prices"
    write_candidate_validation_snapshots(
        (
            _snapshot(
                source_date=source_date,
                symbol="WIN",
                bulltard_source="ranked+interest#1",
                validation_status="confirm",
                detail_rows=2,
            ),
            _snapshot(
                source_date=source_date,
                symbol="LOSE",
                bulltard_source="ranked",
                validation_status="avoid",
                detail_rows=0,
            ),
        ),
        snapshot_root=snapshot_root,
        source_date=source_date,
    )
    _write_price_history(
        price_root,
        symbol="WIN",
        start=source_date,
        closes=[100 + index for index in range(30)],
    )
    _write_price_history(
        price_root,
        symbol="LOSE",
        start=source_date,
        closes=[100 - index for index in range(30)],
    )
    _write_price_history(
        price_root,
        symbol="SPY",
        start=source_date,
        closes=[100 + index * 0.1 for index in range(30)],
    )

    result = compute_bulltard_outcomes(
        start_date=source_date,
        end_date=source_date,
        snapshot_root=snapshot_root,
        price_root=price_root,
        horizons=(20,),
    )

    assert len(result.outcomes) == 2
    all_row = _summary_row(result, "all")
    assert all_row.candidate_count == 2
    assert all_row.available_count == 2
    assert all_row.avg_return == 0.0
    assert all_row.hit_rate == 0.5
    confirm_row = _summary_row(result, "status:confirm")
    assert round(confirm_row.avg_return or 0.0, 4) == 0.2
    assert round(confirm_row.avg_relative_strength_spy or 0.0, 4) == 0.18
    avoid_row = _summary_row(result, "status:avoid")
    assert round(avoid_row.avg_return or 0.0, 4) == -0.2
    assert "source:ranked+interest" in result.table
    assert "status:confirm" in result.table


def _summary_row(result, cohort: str):
    return next(row for row in result.summary_rows if row.cohort == cohort)


def _snapshot(
    *,
    source_date: date,
    symbol: str,
    bulltard_source: str,
    validation_status: str,
    detail_rows: int,
) -> CandidateValidationSnapshot:
    return CandidateValidationSnapshot(
        source_date=source_date,
        feature_version="fixture",
        symbol=symbol,
        bulltard_source=bulltard_source,
        ranked_side="bullish",
        ranked_score=1.0,
        ranked_trade_count=1,
        ranked_premium=1_000_000.0,
        interest_rank=1 if "interest" in bulltard_source else None,
        detail_rows=detail_rows,
        price_date=source_date,
        close=100.0,
        dollar_volume=100_000_000.0,
        return_5d=None,
        return_20d=None,
        return_60d=None,
        ma20_distance=None,
        ma50_distance=None,
        ma200_distance=None,
        drawdown_60d=None,
        relative_strength_20d_spy=None,
        relative_strength_20d_qqq=None,
        underlying_liquidity_status="liquid",
        options_liquidity_status="unknown",
        validation_status=validation_status,
        validation_reasons=("fixture",),
    )


def _write_price_history(
    price_root: Path,
    *,
    symbol: str,
    start: date,
    closes: list[float],
) -> None:
    write_price_observations(
        tuple(
            DailyPriceObservation(
                source="fixture",
                source_symbol=symbol.lower(),
                symbol=symbol,
                observed_date=start + timedelta(days=index),
                open=close,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1_000_000,
            )
            for index, close in enumerate(closes)
        ),
        output_root=price_root,
    )
