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

    assert path == tmp_path / "2026-08-28.jsonl"
    assert loaded == (signal,)


def test_write_market_signal_snapshot_rejects_mixed_dates(tmp_path: Path) -> None:
    first = _signal(source_date=date(2026, 8, 28))
    second = _signal(source_date=date(2026, 8, 29))

    with pytest.raises(MarketSignalError, match="one source date"):
        write_market_signal_snapshot((first, second), snapshot_root=tmp_path)


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
    )

    table = format_market_signals((percent_level, percentage_points))

    assert "2.63%" in table
    assert "+0.42pp" in table


def _signal(*, source_date: date) -> MarketSignal:
    return MarketSignal(
        source_date=source_date,
        feature_version="fixture",
        family="trend",
        name="price_proxy",
        status="constructive",
        score=2,
        value="SPY/QQQ fixture",
        unit="text",
        source="fixture",
        observed_date=source_date,
        availability_date=source_date,
        reason="fixture signal",
    )
