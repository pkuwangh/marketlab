from datetime import date, timedelta
from pathlib import Path

import pytest

from marketlab.charts import ChartError, render_regime_chart
from marketlab.market_signals import MarketSignal, write_market_signal_snapshot
from marketlab.prices import DailyPriceObservation, write_price_observations
from marketlab.regime import RegimeComponentScore, RegimeSnapshot, write_regime_snapshot


def test_render_regime_chart_writes_regime_html(tmp_path: Path) -> None:
    start_date = date(2026, 1, 1)
    end_date = date(2026, 1, 5)
    price_root = tmp_path / "prices"
    regime_root = tmp_path / "regime"
    signal_root = tmp_path / "signals"
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

    result = render_regime_chart(
        start_date=start_date,
        end_date=end_date,
        price_root=price_root,
        regime_snapshot_root=regime_root,
        market_signal_snapshot_root=signal_root,
        output_path=output_path,
    )

    assert result.output_path == output_path
    assert result.price_symbols == ("SPY", "QQQ")
    assert result.price_point_count == 10
    assert result.regime_snapshot_count == 2
    assert result.market_signal_count == 2
    html = output_path.read_text(encoding="utf-8")
    assert "MarketLab Regime Chart" in html
    assert "<svg" in html
    assert "scale_down_protect" in html
    assert "stretch pressure" in html
    assert "Regime component scores" in html
    assert "Market signal family scores" in html
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
