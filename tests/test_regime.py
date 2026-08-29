from datetime import date, timedelta
from pathlib import Path

from marketlab.market_series import MarketSeriesObservation, write_market_series_observations
from marketlab.market_signals import (
    MarketSignal,
    load_market_signal_snapshot,
    write_market_signal_snapshot,
)
from marketlab.prices import DailyPriceObservation, write_price_observations
from marketlab.regime import (
    RegimeComponentScore,
    RegimeSnapshot,
    compute_market_signal_outcomes,
    compute_regime_action_outcomes,
    compute_regime_backfill,
    compute_regime_outcomes,
    compute_regime_pressure_outcomes,
    compute_regime_snapshot,
    derive_regime_action_state,
    load_regime_snapshot,
    refresh_regime_prices,
    write_regime_snapshot,
)


def test_compute_regime_snapshot_scores_constructive_market(tmp_path: Path) -> None:
    source_date = date(2026, 8, 15)
    price_root = tmp_path / "prices"
    market_series_root = tmp_path / "market-series"
    snapshot_root = tmp_path / "snapshots"
    signal_snapshot_root = tmp_path / "signals"
    start = source_date - timedelta(days=229)
    _write_price_history(
        price_root,
        symbol="SPY",
        start=start,
        closes=[100.0 + index * 0.50 for index in range(230)],
    )
    _write_price_history(
        price_root,
        symbol="QQQ",
        start=start,
        closes=[120.0 + index * 0.60 for index in range(230)],
    )
    _write_price_history(
        price_root,
        symbol="RSP",
        start=start,
        closes=[100.0 + index * 0.45 for index in range(230)],
    )
    _write_price_history(
        price_root,
        symbol="IWM",
        start=start,
        closes=[90.0 + index * 0.40 for index in range(230)],
    )
    _write_price_history(
        price_root,
        symbol="HYG",
        start=start,
        closes=[80.0 + index * 0.10 for index in range(230)],
    )
    _write_price_history(
        price_root,
        symbol="TLT",
        start=start,
        closes=[100.0 - index * 0.05 for index in range(230)],
    )
    _write_price_history(
        price_root,
        symbol="^VIX",
        start=start,
        closes=[16.0 for _index in range(230)],
    )
    _write_price_history(
        price_root,
        symbol="^VVIX",
        start=start,
        closes=[85.0 for _index in range(230)],
    )
    _write_market_series_value(
        market_series_root,
        series_id="BAMLH0A0HYM2",
        observed_date=source_date - timedelta(days=1),
        availability_date=source_date,
        value=2.7,
        unit="percent_level",
    )
    _write_market_series_value(
        market_series_root,
        series_id="NFCI",
        observed_date=source_date - timedelta(days=5),
        availability_date=source_date,
        value=-0.5,
        unit="index",
    )
    _write_market_series_value(
        market_series_root,
        series_id="DGS10",
        observed_date=source_date - timedelta(days=1),
        availability_date=source_date,
        value=4.6,
        unit="percent_level",
    )
    _write_market_series_value(
        market_series_root,
        series_id="DGS2",
        observed_date=source_date - timedelta(days=1),
        availability_date=source_date,
        value=4.0,
        unit="percent_level",
    )

    result = compute_regime_snapshot(
        source_date=source_date,
        price_root=price_root,
        market_series_root=market_series_root,
        snapshot_root=snapshot_root,
        signal_snapshot_root=signal_snapshot_root,
    )

    assert result.snapshot_path == snapshot_root / "2026-08-15.json"
    assert result.snapshot_path.is_file()
    assert result.signal_snapshot_path == signal_snapshot_root / "2026-08-15.jsonl"
    assert result.signal_snapshot_path.is_file()
    assert result.snapshot.regime == "risk_on"
    assert result.snapshot.score == 5
    assert result.snapshot.confidence == "high"
    assert result.action is not None
    assert result.action.state == "no_change"
    assert result.snapshot.action_state == "no_change"
    assert result.snapshot.stretch_score == 1
    assert result.snapshot.washout_score == 0
    assert result.pressure is not None
    assert result.snapshot.stretch_pressure_score is not None
    assert result.snapshot.washout_pressure_score is not None
    assert len(result.pressure.features) == 14
    assert "spy_return_20d" in result.pressure_table
    assert result.snapshot.missing_symbols == ()
    assert result.contradictions == ()
    assert [component.name for component in result.snapshot.components] == [
        "trend",
        "volatility",
        "breadth",
        "credit",
    ]
    assert "trend" in result.table
    assert "constructive" in result.table
    assert [(signal.family, signal.name) for signal in result.signals] == [
        ("trend", "price_proxy"),
        ("volatility", "price_proxy"),
        ("breadth", "price_proxy"),
        ("credit", "price_proxy"),
        ("volatility", "vol_of_vol"),
        ("credit", "credit_spread"),
        ("liquidity", "financial_conditions"),
        ("rates", "yield_curve"),
    ]
    assert "price_proxy" in result.signal_table
    assert "vol_of_vol" in result.signal_table
    assert "credit_spread" in result.signal_table
    assert "financial_conditions" in result.signal_table
    assert "yield_curve" in result.signal_table

    loaded_signals = load_market_signal_snapshot(
        source_date=source_date,
        snapshot_root=signal_snapshot_root,
    )
    assert loaded_signals == result.signals

    loaded = load_regime_snapshot(source_date=source_date, snapshot_root=snapshot_root)
    assert loaded == result.snapshot
    assert loaded is not None
    assert loaded.action_state == "no_change"
    assert loaded.stretch_pressure_score == result.snapshot.stretch_pressure_score


def test_compute_regime_snapshot_keeps_missing_components_neutral(tmp_path: Path) -> None:
    source_date = date(2026, 8, 15)
    price_root = tmp_path / "prices"
    _write_price_history(
        price_root,
        symbol="SPY",
        start=source_date - timedelta(days=29),
        closes=[100.0 + index for index in range(30)],
    )

    result = compute_regime_snapshot(
        source_date=source_date,
        price_root=price_root,
        snapshot_root=tmp_path / "snapshots",
        write_snapshot=False,
    )

    assert result.snapshot.regime == "neutral"
    assert result.snapshot.confidence == "low"
    assert "QQQ" in result.snapshot.missing_symbols
    assert "^VVIX" in result.snapshot.missing_symbols
    assert "vol_of_vol" in result.signal_table
    assert "missing" in result.table


def test_compute_regime_backfill_writes_daily_snapshots(tmp_path: Path) -> None:
    end_date = date(2026, 8, 15)
    start = end_date - timedelta(days=229)
    price_root = tmp_path / "prices"
    market_series_root = tmp_path / "market-series"
    snapshot_root = tmp_path / "snapshots"
    signal_snapshot_root = tmp_path / "signals"
    for symbol, base, step in (
        ("SPY", 100.0, 0.50),
        ("QQQ", 120.0, 0.60),
        ("RSP", 100.0, 0.45),
        ("IWM", 90.0, 0.40),
        ("HYG", 80.0, 0.10),
        ("TLT", 100.0, -0.05),
        ("^VIX", 16.0, 0.0),
        ("^VVIX", 85.0, 0.0),
    ):
        _write_price_history(
            price_root,
            symbol=symbol,
            start=start,
            closes=[base + index * step for index in range(230)],
        )
    _write_market_series_value(
        market_series_root,
        series_id="BAMLH0A0HYM2",
        observed_date=end_date - timedelta(days=1),
        availability_date=end_date - timedelta(days=1),
        value=2.7,
        unit="percent_level",
    )
    _write_market_series_value(
        market_series_root,
        series_id="NFCI",
        observed_date=end_date - timedelta(days=5),
        availability_date=end_date - timedelta(days=5),
        value=-0.5,
        unit="index",
    )
    _write_market_series_value(
        market_series_root,
        series_id="DGS10",
        observed_date=end_date - timedelta(days=1),
        availability_date=end_date - timedelta(days=1),
        value=4.6,
        unit="percent_level",
    )
    _write_market_series_value(
        market_series_root,
        series_id="DGS2",
        observed_date=end_date - timedelta(days=1),
        availability_date=end_date - timedelta(days=1),
        value=4.0,
        unit="percent_level",
    )

    result = compute_regime_backfill(
        start_date=end_date - timedelta(days=1),
        end_date=end_date,
        price_root=price_root,
        market_series_root=market_series_root,
        snapshot_root=snapshot_root,
        signal_snapshot_root=signal_snapshot_root,
    )

    assert result.source_dates == (date(2026, 8, 14), date(2026, 8, 15))
    assert len(result.snapshot_paths) == 2
    assert len(result.signal_snapshot_paths) == 2
    assert (snapshot_root / "2026-08-14.json").is_file()
    assert (snapshot_root / "2026-08-15.json").is_file()
    assert (signal_snapshot_root / "2026-08-14.jsonl").is_file()
    assert (signal_snapshot_root / "2026-08-15.jsonl").is_file()
    loaded = load_regime_snapshot(source_date=end_date, snapshot_root=snapshot_root)
    assert loaded is not None
    assert loaded.regime == "risk_on"
    assert loaded.stretch_pressure_score is not None


def test_derive_regime_action_state_flags_stretched_market() -> None:
    snapshot = _snapshot(
        source_date=date(2026, 1, 1),
        regime="risk_on",
        score=5,
        spy_return_20d=0.08,
        spy_return_60d=0.15,
        spy_ma50_distance=0.07,
        qqq_return_20d=0.10,
        qqq_ma50_distance=0.08,
        vix_close=12.5,
        vvix_close=82.0,
    )

    action = derive_regime_action_state(
        snapshot=snapshot,
        signals=(
            _market_signal(
                source_date=snapshot.source_date,
                family="volatility",
                name="vol_of_vol",
                status="calm",
                score=1,
                value=82.0,
            ),
        ),
    )

    assert action.state == "scale_down_protect"
    assert action.stretch_score >= 3
    assert action.washout_score == 0
    assert "Stretched/de-risk threshold crossed" in action.reason


def test_derive_regime_action_state_flags_washout_market() -> None:
    snapshot = _snapshot(
        source_date=date(2026, 1, 1),
        regime="risk_off",
        score=-5,
        components=(
            RegimeComponentScore(
                name="trend",
                score=-2,
                status="weak",
                reason="fixture",
            ),
            RegimeComponentScore(
                name="breadth",
                score=-1,
                status="narrow",
                reason="fixture",
            ),
        ),
        spy_return_20d=-0.10,
        spy_return_60d=-0.16,
        spy_ma50_distance=-0.08,
        qqq_return_20d=-0.13,
        qqq_ma50_distance=-0.10,
        vix_close=34.0,
        vvix_close=130.0,
    )

    action = derive_regime_action_state(
        snapshot=snapshot,
        signals=(
            _market_signal(
                source_date=snapshot.source_date,
                family="volatility",
                name="vol_of_vol",
                status="stressed",
                score=-1,
                value=130.0,
            ),
            _market_signal(
                source_date=snapshot.source_date,
                family="credit",
                name="credit_spread",
                status="mixed",
                score=0,
                value=4.2,
            ),
            _market_signal(
                source_date=snapshot.source_date,
                family="liquidity",
                name="financial_conditions",
                status="neutral",
                score=0,
                value=0.0,
            ),
        ),
    )

    assert action.state == "scale_up_redeploy"
    assert action.washout_score >= 3
    assert action.stretch_score == 0
    assert "Washout/re-risk threshold crossed" in action.reason


def test_derive_regime_action_state_blocks_washout_when_funding_breaks() -> None:
    snapshot = _snapshot(
        source_date=date(2026, 1, 1),
        regime="risk_off",
        score=-5,
        components=(
            RegimeComponentScore(
                name="trend",
                score=-2,
                status="weak",
                reason="fixture",
            ),
        ),
        spy_return_20d=-0.10,
        spy_ma50_distance=-0.08,
        qqq_return_20d=-0.13,
        qqq_ma50_distance=-0.10,
        vix_close=34.0,
        vvix_close=130.0,
    )

    action = derive_regime_action_state(
        snapshot=snapshot,
        signals=(
            _market_signal(
                source_date=snapshot.source_date,
                family="volatility",
                name="vol_of_vol",
                status="stressed",
                score=-1,
                value=130.0,
            ),
            _market_signal(
                source_date=snapshot.source_date,
                family="credit",
                name="credit_spread",
                status="stressed",
                score=-1,
                value=6.5,
            ),
            _market_signal(
                source_date=snapshot.source_date,
                family="liquidity",
                name="financial_conditions",
                status="tight",
                score=-1,
                value=0.4,
            ),
        ),
    )

    assert action.state == "no_change"
    assert action.washout_score >= 3
    assert "block aggressive re-risk" in action.reason


def test_refresh_regime_prices_fetches_default_proxies(tmp_path: Path) -> None:
    calls: list[str] = []

    def downloader(ticker, **kwargs):  # noqa: ANN001, ARG001
        calls.append(ticker)
        import pandas as pd

        frame = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [101.0],
                "Low": [99.0],
                "Close": [100.5],
                "Adj Close": [100.5],
                "Volume": [1_000_000],
            },
            index=pd.to_datetime(["2026-08-14"]),
        )
        frame.index.name = "Date"
        return frame

    result = refresh_regime_prices(
        start_date=date(2026, 8, 14),
        end_date=date(2026, 8, 14),
        price_root=tmp_path / "prices",
        downloader=downloader,
    )

    assert result.requested_symbols == (
        "SPY",
        "QQQ",
        "IWM",
        "RSP",
        "HYG",
        "TLT",
        "^VIX",
        "^VVIX",
    )
    assert calls == list(result.requested_symbols)
    assert len(result.price_results) == 8
    assert result.price_failures == ()


def test_compute_regime_outcomes_summarizes_market_buckets(tmp_path: Path) -> None:
    source_date = date(2026, 1, 1)
    snapshot_root = tmp_path / "snapshots"
    price_root = tmp_path / "prices"
    write_regime_snapshot(
        _snapshot(source_date=source_date, regime="risk_on", score=5),
        snapshot_root=snapshot_root,
    )
    _write_price_history(
        price_root,
        symbol="SPY",
        start=source_date,
        closes=[100.0 + index for index in range(30)],
    )
    _write_price_history(
        price_root,
        symbol="QQQ",
        start=source_date,
        closes=[100.0 + index * 2 for index in range(30)],
    )

    result = compute_regime_outcomes(
        start_date=source_date,
        end_date=source_date,
        snapshot_root=snapshot_root,
        price_root=price_root,
        horizons=(20,),
    )

    assert len(result.outcomes) == 1
    assert result.outcomes[0].regime == "risk_on"
    assert round(result.outcomes[0].spy_return or 0.0, 4) == 0.2
    assert round(result.outcomes[0].qqq_return or 0.0, 4) == 0.4
    assert result.outcomes[0].spy_max_drawdown == 0.0
    assert result.outcomes[0].qqq_max_drawdown == 0.0
    risk_on_row = next(row for row in result.summary_rows if row.bucket == "regime:risk_on")
    assert risk_on_row.snapshot_count == 1
    assert risk_on_row.available_count == 1
    assert round(risk_on_row.avg_spy_return or 0.0, 4) == 0.2
    assert "regime:risk_on" in result.table


def test_compute_regime_outcomes_hides_unavailable_summary_rows(tmp_path: Path) -> None:
    source_date = date(2026, 1, 1)
    snapshot_root = tmp_path / "snapshots"
    price_root = tmp_path / "prices"
    write_regime_snapshot(
        _snapshot(source_date=source_date, regime="risk_on", score=5),
        snapshot_root=snapshot_root,
    )
    _write_price_history(
        price_root,
        symbol="SPY",
        start=source_date,
        closes=[100.0 + index for index in range(30)],
    )
    _write_price_history(
        price_root,
        symbol="QQQ",
        start=source_date,
        closes=[100.0 + index for index in range(30)],
    )

    result = compute_regime_outcomes(
        start_date=source_date,
        end_date=source_date,
        snapshot_root=snapshot_root,
        price_root=price_root,
        horizons=(20, 40),
    )

    assert "20d" in result.table
    assert "40d" not in result.table
    assert "+0.0%" not in result.table


def test_compute_market_signal_outcomes_summarizes_signal_buckets(tmp_path: Path) -> None:
    source_date = date(2026, 1, 1)
    signal_root = tmp_path / "signals"
    price_root = tmp_path / "prices"
    write_market_signal_snapshot(
        (
            MarketSignal(
                source_date=source_date,
                feature_version="fixture",
                family="volatility",
                name="vol_of_vol",
                status="calm",
                score=1,
                value=85.0,
                unit="index",
                source="fixture",
                observed_date=source_date,
                availability_date=source_date,
                reason="fixture",
            ),
        ),
        snapshot_root=signal_root,
    )
    _write_price_history(
        price_root,
        symbol="SPY",
        start=source_date,
        closes=[100.0 + index for index in range(30)],
    )
    _write_price_history(
        price_root,
        symbol="QQQ",
        start=source_date,
        closes=[100.0 + index * 2 for index in range(30)],
    )

    result = compute_market_signal_outcomes(
        start_date=source_date,
        end_date=source_date,
        signal_snapshot_root=signal_root,
        price_root=price_root,
        horizons=(20,),
    )

    assert len(result.outcomes) == 1
    assert result.outcomes[0].family == "volatility"
    assert result.outcomes[0].name == "vol_of_vol"
    assert round(result.outcomes[0].spy_return or 0.0, 4) == 0.2
    signal_row = next(
        row for row in result.summary_rows if row.bucket == "signal:volatility/vol_of_vol/calm"
    )
    assert signal_row.signal_count == 1
    assert signal_row.available_count == 1
    assert "family:volatility" in result.table
    assert "signal:volatility/vol_of_vol/calm" in result.table


def test_compute_regime_action_outcomes_summarizes_action_states(tmp_path: Path) -> None:
    start_date = date(2026, 1, 1)
    snapshot_root = tmp_path / "snapshots"
    price_root = tmp_path / "prices"
    write_regime_snapshot(
        _snapshot(source_date=start_date, regime="risk_on", score=4),
        snapshot_root=snapshot_root,
    )
    write_regime_snapshot(
        _snapshot(
            source_date=start_date + timedelta(days=1),
            regime="risk_on",
            score=5,
            spy_return_20d=0.08,
            spy_return_60d=0.15,
            spy_ma50_distance=0.07,
            qqq_return_20d=0.10,
            qqq_ma50_distance=0.08,
            vix_close=12.0,
        ),
        snapshot_root=snapshot_root,
    )
    write_regime_snapshot(
        _snapshot(
            source_date=start_date + timedelta(days=2),
            regime="risk_off",
            score=-5,
            components=(
                RegimeComponentScore(
                    name="trend",
                    score=-2,
                    status="weak",
                    reason="fixture",
                ),
                RegimeComponentScore(
                    name="breadth",
                    score=-1,
                    status="narrow",
                    reason="fixture",
                ),
            ),
            spy_return_20d=-0.10,
            spy_ma50_distance=-0.08,
            qqq_return_20d=-0.13,
            qqq_ma50_distance=-0.10,
            vix_close=34.0,
        ),
        snapshot_root=snapshot_root,
    )
    _write_price_history(
        price_root,
        symbol="SPY",
        start=start_date,
        closes=[100.0 + index for index in range(40)],
    )
    _write_price_history(
        price_root,
        symbol="QQQ",
        start=start_date,
        closes=[100.0 + index * 2 for index in range(40)],
    )

    result = compute_regime_action_outcomes(
        start_date=start_date,
        end_date=start_date + timedelta(days=2),
        snapshot_root=snapshot_root,
        signal_snapshot_root=tmp_path / "signals",
        price_root=price_root,
        horizons=(20,),
    )

    assert [action.state for action in result.actions] == [
        "no_change",
        "scale_down_protect",
        "scale_up_redeploy",
    ]
    frequency = {row.action_state: row for row in result.frequency_rows}
    assert frequency["no_change"].action_count == 1
    assert frequency["scale_down_protect"].action_count == 1
    assert frequency["scale_up_redeploy"].action_count == 1
    action_row = next(
        row for row in result.summary_rows if row.bucket == "action:scale_up_redeploy"
    )
    assert action_row.action_count == 1
    assert action_row.available_count == 1
    assert round(action_row.avg_spy_return or 0.0, 4) == round(20.0 / 102.0, 4)
    assert "scale_down_protect" in result.frequency_table
    assert "action:scale_up_redeploy" in result.table


def test_compute_regime_pressure_outcomes_summarizes_top_pressure_buckets(
    tmp_path: Path,
) -> None:
    start_date = date(2026, 1, 1)
    snapshot_root = tmp_path / "snapshots"
    price_root = tmp_path / "prices"
    for index in range(35):
        write_regime_snapshot(
            _snapshot(
                source_date=start_date + timedelta(days=index),
                regime="risk_on",
                score=5,
                spy_return_20d=index / 200.0,
                spy_return_60d=index / 180.0,
                spy_ma50_distance=index / 220.0,
                qqq_return_20d=index / 160.0,
                qqq_ma50_distance=index / 180.0,
                spy_realized_vol_20d=0.35 - index / 200.0,
                vix_close=32.0 - index / 2.0,
                vvix_close=130.0 - index,
            ),
            snapshot_root=snapshot_root,
        )
    _write_price_history(
        price_root,
        symbol="SPY",
        start=start_date,
        closes=[100.0 + index for index in range(80)],
    )
    _write_price_history(
        price_root,
        symbol="QQQ",
        start=start_date,
        closes=[100.0 + index * 1.5 for index in range(80)],
    )

    result = compute_regime_pressure_outcomes(
        start_date=start_date + timedelta(days=24),
        end_date=start_date + timedelta(days=34),
        snapshot_root=snapshot_root,
        signal_snapshot_root=tmp_path / "signals",
        price_root=price_root,
        horizons=(20,),
    )

    assert len(result.pressures) == 11
    assert len(result.outcomes) == 11
    stretch_row = next(row for row in result.summary_rows if row.bucket == "stretch:top_10")
    assert stretch_row.pressure_count == 11
    assert stretch_row.available_count == 11
    assert stretch_row.avg_stretch_pressure is not None
    assert stretch_row.avg_stretch_pressure > 0.4
    assert "stretch:top_10" in result.table


def _snapshot(
    *,
    source_date: date,
    regime: str,
    score: int,
    components: tuple[RegimeComponentScore, ...] | None = None,
    spy_return_20d: float | None = 0.05,
    spy_return_60d: float | None = 0.10,
    spy_ma50_distance: float | None = 0.03,
    spy_ma200_distance: float | None = 0.08,
    spy_realized_vol_20d: float | None = 0.12,
    qqq_return_20d: float | None = 0.06,
    qqq_ma50_distance: float | None = 0.04,
    qqq_ma200_distance: float | None = 0.09,
    rsp_spy_relative_20d: float | None = 0.01,
    iwm_spy_relative_20d: float | None = 0.01,
    hyg_tlt_relative_20d: float | None = 0.02,
    vix_close: float | None = 16.0,
    vvix_close: float | None = 85.0,
) -> RegimeSnapshot:
    return RegimeSnapshot(
        source_date=source_date,
        feature_version="fixture_features",
        model_version="fixture_model",
        price_date=source_date,
        regime=regime,
        score=score,
        confidence="high",
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
        spy_ma200_distance=spy_ma200_distance,
        spy_realized_vol_20d=spy_realized_vol_20d,
        qqq_return_20d=qqq_return_20d,
        qqq_ma50_distance=qqq_ma50_distance,
        qqq_ma200_distance=qqq_ma200_distance,
        rsp_spy_relative_20d=rsp_spy_relative_20d,
        iwm_spy_relative_20d=iwm_spy_relative_20d,
        hyg_tlt_relative_20d=hyg_tlt_relative_20d,
        vix_close=vix_close,
        vvix_close=vvix_close,
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


def _write_market_series_value(
    market_series_root: Path,
    *,
    series_id: str,
    observed_date: date,
    availability_date: date,
    value: float,
    unit: str,
) -> None:
    write_market_series_observations(
        (
            MarketSeriesObservation(
                source="fixture",
                source_series_id=series_id,
                series_id=series_id,
                observed_date=observed_date,
                availability_date=availability_date,
                value=value,
                unit=unit,
            ),
        ),
        output_root=market_series_root,
    )


def _market_signal(
    *,
    source_date: date,
    family: str,
    name: str,
    status: str,
    score: int,
    value: float | str | None,
) -> MarketSignal:
    return MarketSignal(
        source_date=source_date,
        feature_version="fixture",
        family=family,
        name=name,
        status=status,
        score=score,
        value=value,
        unit="index" if isinstance(value, float) else "text",
        source="fixture",
        observed_date=source_date,
        availability_date=source_date,
        reason="fixture",
    )
