from datetime import date
from pathlib import Path

import pytest

from marketlab.market_signals import (
    MarketSignal,
    MarketSignalError,
    format_market_signals,
    load_market_signal_snapshot,
    write_market_signal_snapshot,
)


def test_write_and_load_market_signal_snapshot(tmp_path: Path) -> None:
    signal = MarketSignal(
        source_date=date(2026, 8, 28),
        feature_version="fixture",
        family="volatility",
        name="vix_level",
        status="calm",
        score=1,
        value=14.43,
        unit="index",
        source="fixture",
        observed_date=date(2026, 8, 28),
        availability_date=date(2026, 8, 28),
        reason="fixture signal",
    )

    path = write_market_signal_snapshot((signal,), snapshot_root=tmp_path)
    loaded = load_market_signal_snapshot(source_date=date(2026, 8, 28), snapshot_root=tmp_path)

    assert path == _market_signal_snapshot_path(tmp_path, date(2026, 8, 28))
    assert loaded == (signal,)


def test_write_market_signal_snapshot_rejects_mixed_dates(tmp_path: Path) -> None:
    first = _signal(source_date=date(2026, 8, 28))
    second = _signal(source_date=date(2026, 8, 29))

    with pytest.raises(MarketSignalError, match="one source date"):
        write_market_signal_snapshot((first, second), snapshot_root=tmp_path)


def test_write_market_signal_snapshot_replaces_changed_artifact_by_default(
    tmp_path: Path,
) -> None:
    source_date = date(2026, 8, 28)
    first = _signal(source_date=source_date, value="first")
    second = _signal(source_date=source_date, value="second")

    path = write_market_signal_snapshot((first,), snapshot_root=tmp_path)
    rewritten_path = write_market_signal_snapshot((second,), snapshot_root=tmp_path)

    assert rewritten_path == path
    assert load_market_signal_snapshot(source_date=source_date, snapshot_root=tmp_path) == (
        second,
    )


def test_format_market_signals_outputs_compact_table() -> None:
    signal = _signal(source_date=date(2026, 8, 28))

    table = format_market_signals((signal,))

    assert "family" in table
    assert "trend" in table
    assert "+2" in table
    assert "fixture" in table
    assert "2026-08-28" in table


def test_format_market_signals_formats_percent_levels_and_points() -> None:
    percent_level = MarketSignal(
        source_date=date(2026, 8, 28),
        feature_version="fixture",
        family="credit",
        name="credit_spread",
        status="supportive",
        score=1,
        value=2.63,
        unit="percent_level",
        source="fixture",
        observed_date=date(2026, 8, 27),
        availability_date=date(2026, 8, 28),
        reason="fixture signal",
        details={
            "credit_spread_change_5d": 0.08,
            "credit_spread_change_20d": 0.22,
        },
    )
    percentage_points = MarketSignal(
        source_date=date(2026, 8, 28),
        feature_version="fixture",
        family="rates",
        name="yield_curve",
        status="flat",
        score=0,
        value=0.42,
        unit="percentage_points",
        source="fixture",
        observed_date=date(2026, 8, 27),
        availability_date=date(2026, 8, 28),
        reason="fixture signal",
        details={
            "yield_curve_change_5d": 0.06,
            "yield_curve_change_20d": 0.18,
        },
    )
    index_level = MarketSignal(
        source_date=date(2026, 8, 28),
        feature_version="fixture",
        family="liquidity",
        name="financial_conditions",
        status="loose",
        score=1,
        value=-0.56,
        unit="index",
        source="fixture",
        observed_date=date(2026, 8, 27),
        availability_date=date(2026, 8, 28),
        reason="fixture signal",
        details={
            "financial_conditions_change_4w": -0.03,
            "financial_conditions_change_13w": -0.11,
        },
    )

    table = format_market_signals((percent_level, index_level, percentage_points))

    assert "HY OAS 2.63%; 5,20d chg +8/+22bp" in table
    assert "NFCI -0.56; 4,13w chg -0.03/-0.11" in table
    assert "10y-2y +0.42pp; 5,20d chg +6/+18bp" in table


def test_format_market_signals_shows_compact_volatility_values() -> None:
    signal = _signal(
        source_date=date(2026, 8, 28),
        family="volatility",
        name="vol_of_vol",
        score=1,
        value=84.4,
        unit="index",
        details={"vvix_return_5d": 0.12, "vvix_return_20d": -0.04},
    )

    table = format_market_signals((signal,))

    assert "value" in table
    assert "current" not in table
    assert "recent" not in table
    assert "context" not in table
    assert "VVIX 84.40; 5,20d move +12.0%, -4.0%" in table


def test_format_market_signals_shows_compact_cross_asset_values() -> None:
    source_date = date(2026, 8, 28)
    volatility = _signal(
        source_date=source_date,
        family="volatility",
        name="price_proxy",
        score=1,
        value="fallback volatility",
        details={
            "vix_close": 14.53,
            "vix_return_5d": 0.007,
            "vix_return_20d": -0.025,
            "spy_realized_vol_20d": 0.081,
        },
    )
    breadth = _signal(
        source_date=source_date,
        family="breadth",
        name="price_proxy",
        score=1,
        value="fallback breadth",
        details={
            "rsp_spy_relative_5d": 0.004,
            "iwm_spy_relative_5d": -0.003,
            "rsp_spy_relative_20d": -0.001,
            "iwm_spy_relative_20d": -0.014,
        },
    )
    credit = _signal(
        source_date=source_date,
        family="credit",
        name="price_proxy",
        score=0,
        value="fallback credit",
        details={
            "hyg_tlt_relative_5d": 0.002,
            "hyg_tlt_relative_20d": 0.003,
        },
    )

    table = format_market_signals((volatility, breadth, credit))

    assert "VIX 14.53; 5,20d move +0.7%, -2.5%; SPY rv20 +8.1%" in table
    assert "RSP/SPY: 5,20d +0.4/-0.1%; IWM/SPY: 5d,20d -0.3/-1.4%" in table
    assert "HYG/TLT: 5,20d +0.2%, +0.3%" in table


def test_format_market_signals_shows_breadth_participation_values() -> None:
    signal = _signal(
        source_date=date(2026, 9, 4),
        family="breadth",
        name="participation",
        score=-1,
        value=46.91,
        unit="percent_level",
        details={
            "sp500_above_50d": 46.91,
            "sp500_above_200d": 68.78,
            "sp500_above_50d_change_5d": -5.97,
            "sp500_above_200d_change_5d": -1.39,
            "sp500_above_50d_change_20d": -12.45,
            "sp500_above_200d_change_20d": -3.98,
        },
    )

    table = format_market_signals((signal,))

    assert (
        "SPX >50/>200 46.9/68.8%; 5d chg -6.0/-1.4pp; "
        "20d chg -12.4/-4.0pp"
    ) in table


def test_format_market_signals_shows_paired_trend_values() -> None:
    signal = _signal(
        source_date=date(2026, 8, 28),
        details={
            "spy_return_20d": -0.004,
            "qqq_return_20d": -0.006,
            "spy_return_60d": 0.064,
            "qqq_return_60d": 0.052,
            "spy_ma50_distance": 0.018,
            "qqq_ma50_distance": 0.011,
            "spy_ma200_distance": 0.085,
            "qqq_ma200_distance": 0.095,
        },
    )

    table = format_market_signals((signal,))

    assert (
        "SPY/QQQ: 20,60d -0.4/-0.6%, +6.4/+5.2%; "
        "MA50,200 +1.8/+1.1%, +8.5/+9.5%"
    ) in table


def test_format_market_signals_groups_rows_by_family_order() -> None:
    source_date = date(2026, 8, 28)
    table = format_market_signals(
        (
            _signal(source_date=source_date, family="credit", name="credit_spread", score=1),
            _signal(source_date=source_date, family="breadth", name="participation", score=1),
            _signal(source_date=source_date, family="volatility", name="vol_of_vol", score=1),
            _signal(source_date=source_date, family="trend", name="price_proxy", score=2),
            _signal(source_date=source_date, family="volatility", name="price_proxy", score=1),
        )
    )

    assert _row_index(table, "trend", "price_proxy") < _row_index(
        table,
        "volatility",
        "price_proxy",
    )
    assert _row_index(table, "volatility", "price_proxy") < _row_index(
        table,
        "volatility",
        "vol_of_vol",
    )
    assert _row_index(table, "volatility", "vol_of_vol") < _row_index(
        table,
        "breadth",
        "participation",
    )
    assert _row_index(table, "breadth", "participation") < _row_index(
        table,
        "credit",
        "credit_spread",
    )


def _row_index(table: str, family: str, name: str) -> int:
    for index, line in enumerate(table.splitlines()):
        columns = line.split()
        if len(columns) >= 2 and columns[0] == family and columns[1] == name:
            return index
    raise AssertionError(f"Missing market signal row: {family}/{name}")


def _signal(
    *,
    source_date: date,
    family: str = "trend",
    name: str = "price_proxy",
    score: int = 2,
    value: float | str = "SPY/QQQ fixture",
    unit: str = "text",
    details: dict[str, object] | None = None,
) -> MarketSignal:
    return MarketSignal(
        source_date=source_date,
        feature_version="fixture",
        family=family,
        name=name,
        status="constructive",
        score=score,
        value=value,
        unit=unit,
        source="fixture",
        observed_date=source_date,
        availability_date=source_date,
        reason="fixture signal",
        details=details or {},
    )


def _market_signal_snapshot_path(snapshot_root: Path, source_date: date) -> Path:
    source_date_value = source_date.isoformat()
    return (
        snapshot_root
        / source_date_value
        / "eod"
        / f"{source_date_value}_eod"
        / "market_signals_model_v1"
        / "market-signals.jsonl"
    )
