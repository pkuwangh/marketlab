from datetime import date, timedelta
from pathlib import Path

from marketlab.prices import DailyPriceObservation, write_price_observations
from marketlab.regime import (
    compute_regime_snapshot,
    load_regime_snapshot,
    refresh_regime_prices,
)


def test_compute_regime_snapshot_scores_constructive_market(tmp_path: Path) -> None:
    source_date = date(2026, 8, 15)
    price_root = tmp_path / "prices"
    snapshot_root = tmp_path / "snapshots"
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

    result = compute_regime_snapshot(
        source_date=source_date,
        price_root=price_root,
        snapshot_root=snapshot_root,
    )

    assert result.snapshot_path == snapshot_root / "2026-08-15.json"
    assert result.snapshot_path.is_file()
    assert result.snapshot.regime == "risk_on"
    assert result.snapshot.score == 5
    assert result.snapshot.confidence == "high"
    assert result.snapshot.missing_symbols == ()
    assert [component.name for component in result.snapshot.components] == [
        "trend",
        "volatility",
        "breadth",
        "credit",
    ]
    assert "trend" in result.table
    assert "constructive" in result.table

    loaded = load_regime_snapshot(source_date=source_date, snapshot_root=snapshot_root)
    assert loaded == result.snapshot


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
    assert "missing" in result.table


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

    assert result.requested_symbols == ("SPY", "QQQ", "IWM", "RSP", "HYG", "TLT", "^VIX")
    assert calls == list(result.requested_symbols)
    assert len(result.price_results) == 7
    assert result.price_failures == ()


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
