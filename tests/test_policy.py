from datetime import date, timedelta
from pathlib import Path

from marketlab.bulltard.validation import (
    CandidateValidationSnapshot,
    write_candidate_validation_snapshots,
)
from marketlab.market_signals import MarketSignal, write_market_signal_snapshot
from marketlab.policy import (
    compute_daily_policy_report,
    compute_portfolio_policy_backfill,
    compute_portfolio_policy_outcomes,
    compute_portfolio_policy_snapshot,
    derive_portfolio_policy_snapshot,
    load_portfolio_policy_snapshot,
)
from marketlab.prices import DailyPriceObservation, write_price_observations
from marketlab.regime import RegimeComponentScore, RegimeSnapshot, write_regime_snapshot


def test_compute_policy_snapshot_maps_protective_regime_to_bounded_posture(
    tmp_path: Path,
) -> None:
    source_date = date(2026, 8, 28)
    regime_root = tmp_path / "regime"
    signal_root = tmp_path / "signals"
    candidate_root = tmp_path / "candidates"
    policy_root = tmp_path / "policy"
    write_regime_snapshot(
        _regime_snapshot(
            source_date=source_date,
            regime="risk_on",
            score=5,
            action_state="scale_down_protect",
            action_confidence="medium",
            action_reason="Stretched/de-risk threshold crossed",
            stretch_pressure_score=0.72,
            washout_pressure_score=0.10,
        ),
        snapshot_root=regime_root,
    )
    write_candidate_validation_snapshots(
        (
            _candidate(source_date=source_date, symbol="META", validation_status="confirm"),
            _candidate(source_date=source_date, symbol="QXO", validation_status="watch"),
            _candidate(source_date=source_date, symbol="SRRK", validation_status="avoid"),
        ),
        snapshot_root=candidate_root,
        source_date=source_date,
    )

    result = compute_portfolio_policy_snapshot(
        source_date=source_date,
        regime_snapshot_root=regime_root,
        market_signal_snapshot_root=signal_root,
        candidate_snapshot_root=candidate_root,
        policy_snapshot_root=policy_root,
    )

    assert result.snapshot_path == _policy_snapshot_path(policy_root, source_date)
    assert result.snapshot_path.is_file()
    assert result.snapshot.snapshot_version == "v0.0"
    assert result.snapshot.policy_state == "protect"
    assert result.snapshot.marginal_beta_target == 0.90
    assert result.snapshot.candidate_count == 3
    assert result.snapshot.confirm_candidate_count == 1
    assert result.snapshot.candidate_highlights[0].symbol == "META"
    assert result.snapshot.candidate_highlights[0].posture == "reduced_watch"
    assert "covered calls" in result.snapshot.overlay_stance
    assert "protect" in result.table

    loaded = load_portfolio_policy_snapshot(source_date=source_date, snapshot_root=policy_root)
    assert loaded == result.snapshot


def test_derive_policy_snapshot_uses_policy_version_and_preserves_upstream_versions() -> None:
    source_date = date(2026, 8, 28)
    regime_snapshot = _regime_snapshot(
        source_date=source_date,
        action_state="scale_down_protect",
        snapshot_version="regime-v9",
        market_signal_snapshot_version="signal-v9",
    )
    candidate = _candidate(
        source_date=source_date,
        symbol="META",
        validation_status="confirm",
        snapshot_version="bulltard-v9",
    )

    snapshot = derive_portfolio_policy_snapshot(
        regime_snapshot=regime_snapshot,
        candidate_snapshots=(candidate,),
        snapshot_version="policy-v9",
    )

    assert snapshot.snapshot_version == "policy-v9"
    assert snapshot.regime_snapshot_version == "regime-v9"
    assert snapshot.market_signal_snapshot_version == "signal-v9"
    assert snapshot.candidate_snapshot_version == "bulltard-v9"


def test_daily_policy_report_shows_policy_change_and_signal_context(tmp_path: Path) -> None:
    first_date = date(2026, 1, 1)
    second_date = date(2026, 1, 2)
    regime_root = tmp_path / "regime"
    signal_root = tmp_path / "signals"
    policy_root = tmp_path / "policy"
    write_regime_snapshot(
        _regime_snapshot(source_date=first_date, action_state="no_change"),
        snapshot_root=regime_root,
    )
    write_regime_snapshot(
        _regime_snapshot(
            source_date=second_date,
            regime="risk_off",
            score=-4,
            action_state="scale_up_redeploy",
            action_reason="Washout/re-risk threshold crossed",
            stretch_pressure_score=0.05,
            washout_pressure_score=0.85,
        ),
        snapshot_root=regime_root,
    )
    compute_portfolio_policy_snapshot(
        source_date=first_date,
        regime_snapshot_root=regime_root,
        market_signal_snapshot_root=signal_root,
        policy_snapshot_root=policy_root,
    )
    write_market_signal_snapshot(
        (
            MarketSignal(
                source_date=second_date,
                feature_version="fixture",
                family="volatility",
                name="vol_of_vol",
                status="stressed",
                score=-1,
                value=130.0,
                unit="index",
                source="fixture",
                observed_date=second_date,
                availability_date=second_date,
                reason="fixture stress",
            ),
        ),
        snapshot_root=signal_root,
    )

    result = compute_daily_policy_report(
        source_date=second_date,
        regime_snapshot_root=regime_root,
        market_signal_snapshot_root=signal_root,
        policy_snapshot_root=policy_root,
    )

    assert result.policy.policy_state == "redeploy"
    assert result.previous_policy is not None
    assert result.previous_policy.policy_state == "maintain"
    assert "maintain on 2026-01-01 to redeploy" in result.report
    assert "Portfolio posture" in result.report
    assert "vol_of_vol" in result.report
    assert "deploy dry powder in tranches" in result.report


def test_compute_policy_snapshot_uses_saved_regime_action_without_signal_override(
    tmp_path: Path,
) -> None:
    source_date = date(2026, 8, 28)
    regime_root = tmp_path / "regime"
    signal_root = tmp_path / "signals"
    policy_root = tmp_path / "policy"
    write_regime_snapshot(
        _regime_snapshot(
            source_date=source_date,
            action_state="no_change",
            spy_return_20d=0.08,
            spy_return_60d=0.15,
            spy_ma50_distance=0.07,
            qqq_return_20d=0.10,
            qqq_ma50_distance=0.08,
            vix_close=13.0,
            components=(
                RegimeComponentScore(
                    name="trend",
                    score=2,
                    status="constructive",
                    reason="fixture trend",
                ),
                RegimeComponentScore(
                    name="volatility",
                    score=1,
                    status="calm",
                    reason="fixture volatility",
                ),
                RegimeComponentScore(
                    name="breadth",
                    score=0,
                    status="mixed",
                    reason="fixture breadth",
                ),
                RegimeComponentScore(
                    name="credit",
                    score=1,
                    status="risk_appetite",
                    reason="fixture credit",
                ),
            ),
        ),
        snapshot_root=regime_root,
    )
    write_market_signal_snapshot(
        (
            _market_signal(source_date=source_date, family="trend", status="constructive", score=2),
            _market_signal(source_date=source_date, family="volatility", status="calm", score=1),
            _market_signal(source_date=source_date, family="breadth", status="mixed", score=0),
            _market_signal(
                source_date=source_date,
                family="credit",
                status="risk_appetite",
                score=1,
            ),
            _market_signal(
                source_date=source_date,
                family="volatility",
                name="vol_of_vol",
                status="calm",
                score=1,
                value=85.0,
            ),
        ),
        snapshot_root=signal_root,
    )

    result = compute_portfolio_policy_snapshot(
        source_date=source_date,
        regime_snapshot_root=regime_root,
        market_signal_snapshot_root=signal_root,
        policy_snapshot_root=policy_root,
    )

    assert result.snapshot.regime_action_state == "no_change"
    assert result.snapshot.policy_state == "maintain"
    assert result.snapshot.market_signal_snapshot_version is None


def test_policy_backfill_and_outcomes_compare_to_fixed_benchmark(tmp_path: Path) -> None:
    start_date = date(2026, 1, 1)
    regime_root = tmp_path / "regime"
    signal_root = tmp_path / "signals"
    candidate_root = tmp_path / "candidates"
    policy_root = tmp_path / "policy"
    price_root = tmp_path / "prices"
    write_regime_snapshot(
        _regime_snapshot(source_date=start_date, action_state="no_change"),
        snapshot_root=regime_root,
    )
    write_regime_snapshot(
        _regime_snapshot(
            source_date=start_date + timedelta(days=1),
            regime="risk_off",
            score=-4,
            action_state="scale_up_redeploy",
            action_reason="Washout/re-risk threshold crossed",
            stretch_pressure_score=0.05,
            washout_pressure_score=0.90,
        ),
        snapshot_root=regime_root,
    )
    _write_price_history(
        price_root,
        symbol="SPY",
        start=start_date,
        closes=[100.0, 101.0, 102.0, 103.0, 104.0],
    )
    _write_price_history(
        price_root,
        symbol="QQQ",
        start=start_date,
        closes=[100.0, 102.0, 104.0, 106.0, 108.0],
    )

    backfill = compute_portfolio_policy_backfill(
        start_date=start_date,
        end_date=start_date + timedelta(days=1),
        regime_snapshot_root=regime_root,
        market_signal_snapshot_root=signal_root,
        candidate_snapshot_root=candidate_root,
        policy_snapshot_root=policy_root,
    )
    outcome = compute_portfolio_policy_outcomes(
        start_date=start_date,
        end_date=start_date + timedelta(days=1),
        policy_snapshot_root=policy_root,
        price_root=price_root,
        horizons=(2,),
    )

    assert backfill.source_dates == (start_date, start_date + timedelta(days=1))
    assert len(backfill.snapshot_paths) == 2
    assert [policy.policy_state for policy in outcome.policies] == ["maintain", "redeploy"]
    redeploy = next(row for row in outcome.outcomes if row.policy_state == "redeploy")
    assert redeploy.benchmark_return is not None
    assert redeploy.policy_proxy_return is not None
    assert redeploy.policy_proxy_return > redeploy.benchmark_return
    assert redeploy.excess_return is not None
    assert redeploy.excess_return > 0.0
    assert "policy:redeploy" in outcome.table
    assert "====" in outcome.table.splitlines()[1]
    assert "\n---" in outcome.table
    assert "redeploy" in outcome.frequency_table
    assert "====" not in outcome.frequency_table


def _regime_snapshot(
    *,
    source_date: date,
    regime: str = "risk_on",
    score: int = 4,
    components: tuple[RegimeComponentScore, ...] | None = None,
    action_state: str = "no_change",
    action_confidence: str = "medium",
    action_reason: str = "No rare-action threshold crossed",
    stretch_pressure_score: float = 0.30,
    washout_pressure_score: float = 0.20,
    spy_return_20d: float = 0.03,
    spy_return_60d: float = 0.05,
    spy_ma50_distance: float = 0.02,
    qqq_return_20d: float = 0.04,
    qqq_ma50_distance: float = 0.03,
    vix_close: float = 14.0,
    snapshot_version: str | None = None,
    market_signal_snapshot_version: str | None = None,
) -> RegimeSnapshot:
    return RegimeSnapshot(
        source_date=source_date,
        feature_version="fixture_features",
        model_version="fixture_model",
        price_date=source_date,
        regime=regime,
        score=score,
        confidence="medium",
        components=components
        or (
            RegimeComponentScore(
                name="trend",
                score=2,
                status="constructive",
                reason="fixture",
            ),
        ),
        missing_symbols=(),
        spy_return_20d=spy_return_20d,
        spy_return_60d=spy_return_60d,
        spy_ma50_distance=spy_ma50_distance,
        spy_ma200_distance=0.08,
        spy_realized_vol_20d=0.12,
        qqq_return_20d=qqq_return_20d,
        qqq_ma50_distance=qqq_ma50_distance,
        qqq_ma200_distance=0.10,
        rsp_spy_relative_20d=0.0,
        iwm_spy_relative_20d=-0.01,
        hyg_tlt_relative_20d=0.0,
        vix_close=vix_close,
        vvix_close=88.0,
        action_state=action_state,
        action_confidence=action_confidence,
        action_reason=action_reason,
        pressure_confidence="medium",
        stretch_pressure_score=stretch_pressure_score,
        washout_pressure_score=washout_pressure_score,
        snapshot_version=snapshot_version,
        market_signal_snapshot_version=market_signal_snapshot_version,
    )


def _market_signal(
    *,
    source_date: date,
    family: str,
    status: str,
    score: int,
    name: str = "price_proxy",
    value: float | str | None = "fixture",
    unit: str = "text",
) -> MarketSignal:
    return MarketSignal(
        source_date=source_date,
        feature_version="fixture",
        family=family,
        name=name,
        status=status,
        score=score,
        value=value,
        unit=unit,
        source="fixture",
        observed_date=source_date,
        availability_date=source_date,
        reason="fixture signal",
    )


def _candidate(
    *,
    source_date: date,
    symbol: str,
    validation_status: str,
    snapshot_version: str | None = None,
) -> CandidateValidationSnapshot:
    return CandidateValidationSnapshot(
        source_date=source_date,
        feature_version="fixture_candidate",
        symbol=symbol,
        bulltard_source="interest#1",
        ranked_side=None,
        ranked_score=None,
        ranked_trade_count=None,
        ranked_premium=None,
        interest_rank=1,
        detail_rows=5,
        price_date=source_date,
        close=100.0,
        dollar_volume=1_000_000_000.0,
        return_5d=0.01,
        return_20d=0.04,
        return_60d=0.08,
        ma20_distance=0.02,
        ma50_distance=0.03,
        ma200_distance=0.10,
        drawdown_60d=-0.02,
        relative_strength_20d_spy=0.01,
        relative_strength_20d_qqq=0.0,
        underlying_liquidity_status="liquid",
        options_liquidity_status="unknown",
        validation_status=validation_status,
        validation_reasons=("positive_20d", "rs_spy_positive"),
        snapshot_version=snapshot_version,
    )


def _write_price_history(
    price_root: Path,
    *,
    symbol: str,
    start: date,
    closes: list[float],
) -> None:
    rows = tuple(
        DailyPriceObservation(
            source="fixture",
            source_symbol=symbol,
            symbol=symbol,
            observed_date=start + timedelta(days=index),
            open=close - 0.5,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=1_000_000,
            adjusted_close=close,
        )
        for index, close in enumerate(closes)
    )
    write_price_observations(rows, output_root=price_root)


def _policy_snapshot_path(snapshot_root: Path, source_date: date) -> Path:
    source_date_value = source_date.isoformat()
    return (
        snapshot_root
        / source_date_value
        / "eod"
        / "v0.0"
        / "portfolio-policy.json"
    )
