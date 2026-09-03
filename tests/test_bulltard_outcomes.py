import json
from datetime import date, timedelta
from pathlib import Path

from marketlab.bulltard.outcomes import compute_bulltard_outcomes
from marketlab.bulltard.validation import (
    CandidateValidationSnapshot,
    write_candidate_validation_snapshots,
)
from marketlab.prices import DailyPriceObservation, write_price_observations
from marketlab.regime import RegimeComponentScore, RegimeSnapshot, write_regime_snapshot


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
    assert confirm_row.avg_max_drawdown == 0.0
    avoid_row = _summary_row(result, "status:avoid")
    assert round(avoid_row.avg_return or 0.0, 4) == -0.2
    assert round(avoid_row.avg_max_drawdown or 0.0, 4) == -0.2
    assert "source:ranked+interest" in result.table
    assert "status:confirm" in result.table


def test_compute_bulltard_outcomes_hides_unavailable_summary_rows(
    tmp_path: Path,
) -> None:
    source_date = date(2026, 1, 1)
    snapshot_root = tmp_path / "snapshots"
    price_root = tmp_path / "prices"
    write_candidate_validation_snapshots(
        (
            _snapshot(
                source_date=source_date,
                symbol="META",
                bulltard_source="ranked",
                validation_status="confirm",
                detail_rows=1,
            ),
        ),
        snapshot_root=snapshot_root,
        source_date=source_date,
    )
    _write_price_history(
        price_root,
        symbol="META",
        start=source_date,
        closes=[100.0 + index for index in range(30)],
    )
    _write_price_history(
        price_root,
        symbol="SPY",
        start=source_date,
        closes=[100.0 for _index in range(30)],
    )

    result = compute_bulltard_outcomes(
        start_date=source_date,
        end_date=source_date,
        snapshot_root=snapshot_root,
        price_root=price_root,
        horizons=(20, 40),
    )

    assert "signals" in result.table
    assert "20d" in result.table
    assert "40d" not in result.table
    assert "+0.0%" not in result.table


def test_compute_bulltard_outcomes_uses_adjusted_close_for_returns(tmp_path: Path) -> None:
    source_date = date(2026, 1, 1)
    snapshot_root = tmp_path / "snapshots"
    price_root = tmp_path / "prices"
    write_candidate_validation_snapshots(
        (
            _snapshot(
                source_date=source_date,
                symbol="ADJ",
                bulltard_source="ranked",
                validation_status="confirm",
                detail_rows=1,
            ),
        ),
        snapshot_root=snapshot_root,
        source_date=source_date,
    )
    _write_price_history(
        price_root,
        symbol="ADJ",
        start=source_date,
        closes=[100.0 for _index in range(30)],
        adjusted_closes=[100 + index for index in range(30)],
    )
    _write_price_history(
        price_root,
        symbol="SPY",
        start=source_date,
        closes=[100.0 for _index in range(30)],
        adjusted_closes=[100.0 for _index in range(30)],
    )

    result = compute_bulltard_outcomes(
        start_date=source_date,
        end_date=source_date,
        snapshot_root=snapshot_root,
        price_root=price_root,
        horizons=(20,),
    )

    assert round(result.outcomes[0].return_value or 0.0, 4) == 0.2
    assert round(result.outcomes[0].relative_strength_spy or 0.0, 4) == 0.2


def test_compute_bulltard_outcomes_summarizes_flow_and_regime_cohorts(
    tmp_path: Path,
) -> None:
    source_date = date(2026, 1, 1)
    snapshot_root = tmp_path / "snapshots"
    price_root = tmp_path / "prices"
    observations_root = tmp_path / "observations" / "bulltard"
    regime_snapshot_root = tmp_path / "regime-snapshots"
    write_candidate_validation_snapshots(
        (
            _snapshot(
                source_date=source_date,
                symbol="PSLD",
                bulltard_source="ranked+interest#1",
                validation_status="confirm",
                detail_rows=1,
                ranked_side="bullish",
            ),
            _snapshot(
                source_date=source_date,
                symbol="CALL",
                bulltard_source="ranked",
                validation_status="watch",
                detail_rows=1,
                ranked_side="bullish",
            ),
        ),
        snapshot_root=snapshot_root,
        source_date=source_date,
    )
    _write_ticker_flow(
        observations_root,
        source_date=source_date,
        symbol="PSLD",
        order_types=("Puts Sold",),
    )
    _write_ticker_flow(
        observations_root,
        source_date=source_date,
        symbol="CALL",
        order_types=("Calls Bought",),
    )
    write_regime_snapshot(
        _regime_snapshot(
            source_date=source_date,
            regime="risk_off",
            action_state="scale_up_redeploy",
        ),
        snapshot_root=regime_snapshot_root,
    )
    _write_price_history(
        price_root,
        symbol="PSLD",
        start=source_date,
        closes=[100 + index for index in range(70)],
    )
    _write_price_history(
        price_root,
        symbol="CALL",
        start=source_date,
        closes=[100 - index * 0.5 for index in range(70)],
    )
    _write_price_history(
        price_root,
        symbol="SPY",
        start=source_date,
        closes=[100.0 for _index in range(70)],
    )

    result = compute_bulltard_outcomes(
        start_date=source_date,
        end_date=source_date,
        snapshot_root=snapshot_root,
        price_root=price_root,
        observations_root=observations_root,
        regime_snapshot_root=regime_snapshot_root,
        horizons=(65,),
    )

    put_selling = _summary_row(result, "flow:put_selling")
    assert put_selling.available_count == 1
    assert round(put_selling.avg_return or 0.0, 4) == 0.65
    assert round(put_selling.avg_max_runup or 0.0, 4) == 0.65
    call_buying = _summary_row(result, "flow:call_buying")
    assert round(call_buying.avg_return or 0.0, 4) == -0.325
    regime = _summary_row(result, "regime:risk_off")
    assert regime.candidate_count == 2
    assert _summary_row(result, "action:scale_up_redeploy").candidate_count == 2
    assert _summary_row(result, "ranked_side:bullish").candidate_count == 2
    assert "flow_regime:put_selling/risk_off" in result.table
    assert "status_regime:confirm/risk_off" in result.table


def _summary_row(result, cohort: str):
    return next(row for row in result.summary_rows if row.cohort == cohort)


def _snapshot(
    *,
    source_date: date,
    symbol: str,
    bulltard_source: str,
    validation_status: str,
    detail_rows: int,
    ranked_side: str | None = "bullish",
) -> CandidateValidationSnapshot:
    return CandidateValidationSnapshot(
        source_date=source_date,
        feature_version="fixture",
        symbol=symbol,
        bulltard_source=bulltard_source,
        ranked_side=ranked_side,
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
    adjusted_closes: list[float | None] | None = None,
) -> None:
    adjusted_values = adjusted_closes or [None for _close in closes]
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
                adjusted_close=adjusted_values[index],
            )
            for index, close in enumerate(closes)
        ),
        output_root=price_root,
    )


def _write_ticker_flow(
    observations_root: Path,
    *,
    source_date: date,
    symbol: str,
    order_types: tuple[str, ...],
) -> None:
    path = observations_root / "ticker_flow" / symbol / f"{source_date.isoformat()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "source": "bulltard",
            "source_date": source_date.isoformat(),
            "view": "ticker-flow-history",
            "symbol": symbol,
            "traded_at": f"{source_date.isoformat()}T10:{index:02d}",
            "order_type": order_type,
            "side": "bullish",
            "contract": "100P",
            "contract_type": "put",
            "expiry": "2026-06-19",
            "contracts": 100,
            "premium": 1_000_000.0,
            "is_older": False,
        }
        for index, order_type in enumerate(order_types)
    ]
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n")


def _regime_snapshot(
    *,
    source_date: date,
    regime: str,
    action_state: str,
) -> RegimeSnapshot:
    return RegimeSnapshot(
        source_date=source_date,
        feature_version="fixture_features",
        model_version="fixture_model",
        price_date=source_date,
        regime=regime,
        score=-3,
        confidence="medium",
        components=(
            RegimeComponentScore(
                name="trend",
                score=-2,
                status="weak",
                reason="fixture",
            ),
        ),
        missing_symbols=(),
        spy_return_20d=-0.1,
        spy_return_60d=-0.2,
        spy_ma50_distance=-0.05,
        spy_ma200_distance=-0.1,
        spy_realized_vol_20d=0.25,
        qqq_return_20d=-0.12,
        qqq_ma50_distance=-0.08,
        qqq_ma200_distance=-0.12,
        rsp_spy_relative_20d=-0.01,
        iwm_spy_relative_20d=-0.03,
        hyg_tlt_relative_20d=-0.02,
        vix_close=35.0,
        vvix_close=120.0,
        action_state=action_state,
        action_confidence="medium",
        action_reason="fixture",
    )
