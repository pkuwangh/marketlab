import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from marketlab.bulltard.validation import (
    CandidateValidationSnapshot,
    write_candidate_validation_snapshots,
)
from marketlab.charts import ChartError, render_opportunity_chart, render_regime_chart
from marketlab.market_signals import MarketSignal, write_market_signal_snapshot
from marketlab.policy import PortfolioPolicySnapshot, write_portfolio_policy_snapshot
from marketlab.prices import DailyPriceObservation, write_price_observations
from marketlab.regime import RegimeComponentScore, RegimeSnapshot, write_regime_snapshot


def test_render_regime_chart_writes_regime_html(tmp_path: Path) -> None:
    start_date = date(2026, 1, 1)
    end_date = date(2026, 1, 5)
    price_root = tmp_path / "prices"
    regime_root = tmp_path / "regime"
    signal_root = tmp_path / "signals"
    policy_root = tmp_path / "policy"
    output_path = tmp_path / "reports" / "regime.html"
    _write_price_history(
        price_root,
        symbol="SPY",
        start=start_date,
        closes=[100.0, 101.0, 102.0, 101.5, 103.0],
    )
    _write_price_history(
        price_root,
        symbol="QQQ",
        start=start_date,
        closes=[100.0, 102.0, 101.0, 103.0, 104.0],
    )
    write_regime_snapshot(
        _regime_snapshot(
            source_date=start_date,
            action_state="no_change",
            stretch_pressure_score=0.20,
            washout_pressure_score=0.10,
        ),
        snapshot_root=regime_root,
    )
    write_regime_snapshot(
        _regime_snapshot(
            source_date=end_date,
            action_state="scale_down_protect",
            stretch_pressure_score=0.80,
            washout_pressure_score=0.15,
        ),
        snapshot_root=regime_root,
    )
    write_market_signal_snapshot(
        (
            _market_signal(
                source_date=end_date,
                family="volatility",
                name="vol_of_vol",
                status="calm",
                score=1,
                value=85.0,
                unit="index",
            ),
            _market_signal(
                source_date=end_date,
                family="credit",
                name="credit_spread",
                status="supportive",
                score=1,
                value=3.1,
                unit="percent_level",
            ),
        ),
        snapshot_root=signal_root,
    )
    write_portfolio_policy_snapshot(
        _policy_snapshot(source_date=end_date, policy_state="protect"),
        snapshot_root=policy_root,
    )

    result = render_regime_chart(
        start_date=start_date,
        end_date=end_date,
        price_root=price_root,
        regime_snapshot_root=regime_root,
        market_signal_snapshot_root=signal_root,
        policy_snapshot_root=policy_root,
        output_path=output_path,
    )

    assert result.output_path == output_path
    assert result.price_symbols == ("SPY", "QQQ")
    assert result.price_point_count == 10
    assert result.regime_snapshot_count == 2
    assert result.market_signal_count == 2
    assert result.policy_snapshot_count == 1
    html = output_path.read_text(encoding="utf-8")
    assert "MarketLab Regime Chart" in html
    assert "<svg" in html
    assert "scale_down_protect" in html
    assert "stretch pressure" in html
    assert "Regime component scores" in html
    assert "Market signal family scores" in html
    assert "Portfolio policy state" in html
    assert "target_beta=0.9" in html
    assert "vol_of_vol" in html
    assert "credit_spread" in html


def test_render_regime_chart_requires_regime_snapshots(tmp_path: Path) -> None:
    start_date = date(2026, 1, 1)
    price_root = tmp_path / "prices"
    _write_price_history(
        price_root,
        symbol="SPY",
        start=start_date,
        closes=[100.0, 101.0],
    )

    with pytest.raises(ChartError, match="No regime snapshots found"):
        render_regime_chart(
            start_date=start_date,
            end_date=start_date + timedelta(days=1),
            price_root=price_root,
            regime_snapshot_root=tmp_path / "regime",
            market_signal_snapshot_root=tmp_path / "signals",
            output_path=tmp_path / "regime.html",
        )


def test_render_opportunity_chart_writes_candidate_html(tmp_path: Path) -> None:
    source_date = date(2026, 1, 31)
    price_root = tmp_path / "prices"
    snapshot_root = tmp_path / "candidates"
    observations_root = tmp_path / "observations" / "bulltard"
    output_path = tmp_path / "reports" / "opportunity.html"
    _write_price_history(
        price_root,
        symbol="MRVL",
        start=date(2026, 1, 1),
        closes=[100.0 + index * 0.7 for index in range(170)],
    )
    _write_price_history(
        price_root,
        symbol="SPY",
        start=date(2026, 1, 1),
        closes=[100.0 + index * 0.2 for index in range(170)],
    )
    _write_price_history(
        price_root,
        symbol="QQQ",
        start=date(2026, 1, 1),
        closes=[100.0 + index * 0.3 for index in range(170)],
    )
    write_candidate_validation_snapshots(
        (
            _candidate_validation_snapshot(
                source_date=source_date,
                symbol="MRVL",
            ),
        ),
        snapshot_root=snapshot_root,
        source_date=source_date,
    )
    _write_jsonl(
        observations_root / "ticker_flow" / "MRVL" / "2026-01-31.jsonl",
        [
            {
                "source_date": "2026-01-31",
                "symbol": "MRVL",
                "traded_at": "2026-01-31T10:15",
                "order_type": "Puts Sold",
                "side": "bullish",
                "contract": "90P",
                "contract_type": "put",
                "expiry": "2026-03-20",
                "contracts": 1000,
                "premium": 2_500_000.0,
                "is_older": False,
            },
            {
                "source_date": "2026-01-31",
                "symbol": "MRVL",
                "traded_at": "2026-01-30T11:10",
                "order_type": "Puts Bought",
                "side": "bearish",
                "contract": "95P",
                "contract_type": "put",
                "expiry": "2026-02-20",
                "contracts": 500,
                "premium": 750_000.0,
                "is_older": False,
            },
        ],
    )
    _write_jsonl(
        observations_root / "trades_of_interest" / "2026-01-31.jsonl",
        [
            {
                "source": "bulltard",
                "source_date": "2026-01-31",
                "view": "trades-of-interest",
                "rank": 2,
                "symbol": "MRVL",
                "note": "Fixture multi-month opportunity note.",
            }
        ],
    )

    result = render_opportunity_chart(
        source_date=source_date,
        symbol="MRVL",
        lookback_days=25,
        forward_days=10,
        price_root=price_root,
        candidate_snapshot_root=snapshot_root,
        observations_root=observations_root,
        output_path=output_path,
    )

    assert result.output_path == output_path
    assert result.symbol == "MRVL"
    assert result.price_symbols == ("MRVL", "SPY", "QQQ")
    assert result.flow_event_count == 2
    assert result.available_forward_outcome_count == 6
    assert result.validation_status == "watch"
    html = output_path.read_text(encoding="utf-8")
    assert "MRVL Opportunity Chart" in html
    assert "<svg" in html
    assert "Bulltard flow premium by trade date" in html
    assert "20d relative strength" in html
    assert "Point-In-Time Candidate Snapshot" in html
    assert "Fixture multi-month opportunity note." in html
    assert "Puts Sold" in html
    assert "Forward Outcomes" in html
    assert "1 trading rows" in html


def test_render_opportunity_chart_requires_candidate_snapshot(tmp_path: Path) -> None:
    with pytest.raises(ChartError, match="No Bulltard candidate validation snapshots found"):
        render_opportunity_chart(
            source_date=date(2026, 1, 31),
            symbol="MRVL",
            price_root=tmp_path / "prices",
            candidate_snapshot_root=tmp_path / "candidates",
            observations_root=tmp_path / "observations",
            output_path=tmp_path / "opportunity.html",
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
        ),
        output_root=price_root,
    )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8")


def _candidate_validation_snapshot(
    *,
    source_date: date,
    symbol: str,
) -> CandidateValidationSnapshot:
    return CandidateValidationSnapshot(
        source_date=source_date,
        feature_version="fixture_validation",
        symbol=symbol,
        bulltard_source="ranked+interest#2",
        ranked_side="bullish",
        ranked_score=10.0,
        ranked_trade_count=12,
        ranked_premium=24_000_000.0,
        interest_rank=2,
        detail_rows=2,
        price_date=source_date,
        close=121.0,
        dollar_volume=200_000_000.0,
        return_5d=0.03,
        return_20d=0.10,
        return_60d=0.18,
        ma20_distance=0.05,
        ma50_distance=-0.03,
        ma200_distance=0.08,
        drawdown_60d=-0.12,
        relative_strength_20d_spy=0.04,
        relative_strength_20d_qqq=0.03,
        underlying_liquidity_status="liquid",
        options_liquidity_status="unknown",
        validation_status="watch",
        validation_reasons=("positive_20d", "rs_spy_positive"),
    )


def _regime_snapshot(
    *,
    source_date: date,
    action_state: str,
    stretch_pressure_score: float,
    washout_pressure_score: float,
) -> RegimeSnapshot:
    return RegimeSnapshot(
        source_date=source_date,
        feature_version="fixture_features",
        model_version="fixture_model",
        price_date=source_date,
        regime="risk_on",
        score=4,
        confidence="medium",
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
                score=1,
                status="broad",
                reason="fixture breadth",
            ),
            RegimeComponentScore(
                name="credit",
                score=0,
                status="mixed",
                reason="fixture credit",
            ),
        ),
        missing_symbols=(),
        spy_return_20d=0.03,
        spy_return_60d=0.05,
        spy_ma50_distance=0.02,
        spy_ma200_distance=0.08,
        spy_realized_vol_20d=0.12,
        qqq_return_20d=0.04,
        qqq_ma50_distance=0.03,
        qqq_ma200_distance=0.10,
        rsp_spy_relative_20d=0.0,
        iwm_spy_relative_20d=-0.01,
        hyg_tlt_relative_20d=0.0,
        vix_close=14.0,
        vvix_close=85.0,
        action_state=action_state,
        action_confidence="medium",
        action_reason="fixture action",
        stretch_score=1,
        washout_score=0,
        stretch_pressure_score=stretch_pressure_score,
        washout_pressure_score=washout_pressure_score,
        pressure_confidence="medium",
    )


def _policy_snapshot(*, source_date: date, policy_state: str) -> PortfolioPolicySnapshot:
    return PortfolioPolicySnapshot(
        source_date=source_date,
        policy_version="fixture_policy",
        regime="risk_on",
        regime_score=4,
        regime_confidence="medium",
        regime_price_date=source_date,
        regime_action_state="scale_down_protect",
        regime_action_confidence="medium",
        regime_action_reason="fixture action",
        stretch_score=3,
        washout_score=0,
        stretch_pressure_score=0.8,
        washout_pressure_score=0.1,
        pressure_confidence="medium",
        policy_state=policy_state,
        policy_confidence="medium",
        marginal_beta_target=0.9,
        marginal_beta_range="0.85-0.95 tactical beta",
        cash_posture="raise or preserve cash",
        long_delta_stance="avoid fresh long calls",
        overlay_stance="consider covered calls",
        put_underwriting_stance="prefer defined risk",
        single_name_risk_budget="reduced",
        candidate_count=0,
        confirm_candidate_count=0,
        watch_candidate_count=0,
        avoid_candidate_count=0,
        candidate_highlights=(),
        rationale=("fixture",),
    )


def _market_signal(
    *,
    source_date: date,
    family: str,
    name: str,
    status: str,
    score: int,
    value: float,
    unit: str,
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
