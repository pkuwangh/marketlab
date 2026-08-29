from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import pytest

from marketlab.prices import (
    PriceDataError,
    fetch_and_write_stooq_daily_prices,
    fetch_and_write_yahoo_daily_prices,
    import_daily_price_csv,
    load_price_history,
    parse_stooq_daily_csv,
    parse_yahoo_daily_frame,
    to_stooq_symbol,
)


def test_fetch_and_write_stooq_daily_prices_merges_deduped_symbols(tmp_path: Path) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            text=(
                "Date,Open,High,Low,Close,Volume\n"
                "2026-08-24,100,105,99,104,1000000\n"
                "2026-08-25,104,108,103,107,1200000\n"
            ),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    output_root = tmp_path / "prices"

    results = fetch_and_write_stooq_daily_prices(
        symbols=("meta", "META", "SPY"),
        start_date=date(2026, 8, 24),
        end_date=date(2026, 8, 25),
        output_root=output_root,
        api_key="fixture-key",
        client=client,
    )

    assert [result.symbol for result in results] == ["META", "SPY"]
    assert len(requested_urls) == 2
    assert "s=meta.us" in requested_urls[0]
    assert "apikey=fixture-key" in requested_urls[0]
    assert (output_root / "META.jsonl").is_file()
    assert (output_root / "SPY.jsonl").is_file()
    meta_history = load_price_history(symbol="META", price_root=output_root)
    assert [row.close for row in meta_history] == [104.0, 107.0]


def test_parse_stooq_daily_csv_rejects_error_payload() -> None:
    with pytest.raises(PriceDataError, match="apikey"):
        parse_stooq_daily_csv(
            "apikey required\n",
            symbol="META",
            source_symbol="meta.us",
        )


def test_import_daily_price_csv_writes_local_observations(tmp_path: Path) -> None:
    csv_path = tmp_path / "meta.csv"
    csv_path.write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        "2026-08-24,100,105,99,104,103.50,1000000\n"
        "2026-08-25,104,108,103,107,106.50,1200000\n",
        encoding="utf-8",
    )

    result = import_daily_price_csv(
        symbol="META",
        csv_path=csv_path,
        output_root=tmp_path / "prices",
        source="fixture",
        source_symbol="meta.us",
    )

    assert result.symbol == "META"
    assert result.source_symbol == "meta.us"
    assert result.row_count == 2
    rows = load_price_history(symbol="META", price_root=tmp_path / "prices")
    assert rows[0].source == "fixture"
    assert rows[1].close == 107.0
    assert rows[1].adjusted_close == 106.5


def test_parse_yahoo_daily_frame_reads_adjusted_close() -> None:
    frame = pd.DataFrame(
        {
            "Open": [100.0, 104.0],
            "High": [105.0, 108.0],
            "Low": [99.0, 103.0],
            "Close": [104.0, 107.0],
            "Adj Close": [103.5, 106.5],
            "Volume": [1_000_000, 1_200_000],
        },
        index=pd.to_datetime(["2026-08-24", "2026-08-25"]),
    )
    frame.index.name = "Date"

    rows = parse_yahoo_daily_frame(
        frame,
        symbol="meta",
        start_date=date(2026, 8, 24),
        end_date=date(2026, 8, 25),
    )

    assert [row.source for row in rows] == ["yahoo", "yahoo"]
    assert [row.symbol for row in rows] == ["META", "META"]
    assert rows[0].observed_date == date(2026, 8, 24)
    assert rows[1].adjusted_close == 106.5
    assert rows[1].return_close == 106.5


def test_parse_yahoo_daily_frame_skips_incomplete_trailing_row() -> None:
    frame = pd.DataFrame(
        {
            "Open": [100.0, 104.0],
            "High": [105.0, 108.0],
            "Low": [99.0, 103.0],
            "Close": [104.0, float("nan")],
            "Adj Close": [103.5, float("nan")],
            "Volume": [1_000_000, 1_200_000],
        },
        index=pd.to_datetime(["2026-08-24", "2026-08-25"]),
    )
    frame.index.name = "Date"

    rows = parse_yahoo_daily_frame(
        frame,
        symbol="meta",
        start_date=date(2026, 8, 24),
        end_date=date(2026, 8, 25),
    )

    assert [row.observed_date for row in rows] == [date(2026, 8, 24)]


def test_parse_yahoo_daily_frame_rejects_incomplete_middle_row() -> None:
    frame = pd.DataFrame(
        {
            "Open": [100.0, 104.0, 107.0],
            "High": [105.0, 108.0, 110.0],
            "Low": [99.0, 103.0, 106.0],
            "Close": [104.0, float("nan"), 109.0],
            "Adj Close": [103.5, float("nan"), 108.5],
            "Volume": [1_000_000, 1_200_000, 1_100_000],
        },
        index=pd.to_datetime(["2026-08-24", "2026-08-25", "2026-08-26"]),
    )
    frame.index.name = "Date"

    with pytest.raises(PriceDataError, match="Invalid Yahoo price row 2"):
        parse_yahoo_daily_frame(
            frame,
            symbol="meta",
            start_date=date(2026, 8, 24),
            end_date=date(2026, 8, 26),
        )


def test_fetch_and_write_yahoo_daily_prices_uses_downloader(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def downloader(ticker, **kwargs):
        calls.append({"ticker": ticker, **kwargs})
        frame = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [105.0],
                "Low": [99.0],
                "Close": [104.0],
                "Adj Close": [103.5],
                "Volume": [1_000_000],
            },
            index=pd.to_datetime(["2026-08-24"]),
        )
        frame.index.name = "Date"
        return frame

    results = fetch_and_write_yahoo_daily_prices(
        symbols=("meta", "META", "SPY"),
        start_date=date(2026, 8, 24),
        end_date=date(2026, 8, 24),
        output_root=tmp_path / "prices",
        downloader=downloader,
    )

    assert [result.symbol for result in results] == ["META", "SPY"]
    assert [call["ticker"] for call in calls] == ["META", "SPY"]
    assert calls[0]["auto_adjust"] is False
    assert calls[0]["end"] == "2026-08-25"
    rows = load_price_history(symbol="META", price_root=tmp_path / "prices")
    assert rows[0].source == "yahoo"
    assert rows[0].adjusted_close == 103.5


def test_to_stooq_symbol_adds_us_suffix_only_when_needed() -> None:
    assert to_stooq_symbol("META") == "meta.us"
    assert to_stooq_symbol("BRK.B") == "brk.b.us"
    assert to_stooq_symbol("BMW.DE") == "bmw.de"
    assert to_stooq_symbol("^SPX") == "^spx"
