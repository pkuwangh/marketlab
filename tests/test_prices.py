import json
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import pytest

from marketlab.prices import (
    DailyPriceObservation,
    PriceDataError,
    fetch_and_write_cboe_index_daily_prices,
    fetch_and_write_eoddata_index_daily_prices,
    fetch_and_write_stooq_daily_prices,
    fetch_and_write_yahoo_daily_prices,
    import_daily_price_csv,
    load_price_history,
    parse_cboe_index_daily_csv,
    parse_eoddata_index_daily_html,
    parse_stooq_daily_csv,
    parse_yahoo_daily_frame,
    price_observation_path,
    to_cboe_index_symbol,
    to_eoddata_index_symbol,
    to_stooq_symbol,
    write_price_observations,
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


def test_write_price_observations_refuses_same_date_correction(tmp_path: Path) -> None:
    first = _price_row(close=104.0)
    corrected = _price_row(close=105.0)
    output_root = tmp_path / "prices"

    write_price_observations((first,), output_root=output_root)

    with pytest.raises(PriceDataError, match="Refusing to overwrite"):
        write_price_observations((corrected,), output_root=output_root)


def test_index_price_observations_use_safe_filename_and_load_legacy_path(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "prices"
    vix_row = _price_row(close=18.0, symbol="^VIX")

    path = write_price_observations((vix_row,), output_root=output_root)

    assert path == output_root / "INDEX_VIX.jsonl"
    assert price_observation_path(symbol="^VIX", price_root=output_root) == path
    assert not (output_root / "^VIX.jsonl").exists()
    assert load_price_history(symbol="^VIX", price_root=output_root)[0].symbol == "^VIX"

    breadth_row = _price_row(close=46.9, symbol="$S5FI")
    breadth_path = write_price_observations((breadth_row,), output_root=output_root)

    assert breadth_path == output_root / "INDEX_S5FI.jsonl"
    assert price_observation_path(symbol="$S5FI", price_root=output_root) == breadth_path
    assert not (output_root / "$S5FI.jsonl").exists()
    assert load_price_history(symbol="$S5FI", price_root=output_root)[0].symbol == "$S5FI"

    legacy_row = _price_row(close=90.0, symbol="^VVIX")
    legacy_path = output_root / "^VVIX.jsonl"
    legacy_path.write_text(json.dumps(legacy_row.to_dict(), sort_keys=True) + "\n")

    legacy_rows = load_price_history(symbol="^VVIX", price_root=output_root)
    assert len(legacy_rows) == 1
    assert legacy_rows[0].symbol == "^VVIX"
    assert legacy_rows[0].close == 90.0


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


def test_parse_cboe_index_daily_csv_reads_ohlc_rows() -> None:
    rows = parse_cboe_index_daily_csv(
        "DATE,OPEN,HIGH,LOW,CLOSE\n"
        "09/03/2026,13.10,13.80,12.90,13.20\n"
        "09/04/2026,13.20,14.00,12.70,13.50\n",
        symbol="^VIX9D",
        source_symbol="VIX9D",
        start_date=date(2026, 9, 4),
        end_date=date(2026, 9, 4),
    )

    assert len(rows) == 1
    assert rows[0].source == "cboe"
    assert rows[0].source_symbol == "VIX9D"
    assert rows[0].symbol == "^VIX9D"
    assert rows[0].observed_date == date(2026, 9, 4)
    assert rows[0].open == 13.2
    assert rows[0].high == 14.0
    assert rows[0].low == 12.7
    assert rows[0].close == 13.5
    assert rows[0].volume == 0
    assert rows[0].adjusted_close == 13.5


def test_parse_cboe_index_daily_csv_reads_single_value_rows() -> None:
    rows = parse_cboe_index_daily_csv(
        "DATE,VVIX\n"
        "2026-09-03,85.2\n"
        "2026-09-04,86.4\n",
        symbol="^VVIX",
        source_symbol="VVIX",
        start_date=date(2026, 9, 3),
        end_date=date(2026, 9, 4),
    )

    assert [row.close for row in rows] == [85.2, 86.4]
    assert rows[0].open == 85.2
    assert rows[0].high == 85.2
    assert rows[0].low == 85.2


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


def test_fetch_and_write_cboe_index_daily_prices_uses_public_csv(
    tmp_path: Path,
) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            text=(
                "DATE,OPEN,HIGH,LOW,CLOSE\n"
                "09/04/2026,13.20,14.00,12.70,13.50\n"
            ),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    results = fetch_and_write_cboe_index_daily_prices(
        symbols=("VIX9D", "^VIX9D"),
        start_date=date(2026, 9, 4),
        end_date=date(2026, 9, 4),
        output_root=tmp_path / "prices",
        client=client,
    )

    assert len(results) == 1
    assert results[0].symbol == "^VIX9D"
    assert results[0].source_symbol == "VIX9D"
    assert results[0].observation_path.name == "INDEX_VIX9D.jsonl"
    assert requested_urls == [
        "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX9D_History.csv"
    ]
    rows = load_price_history(symbol="^VIX9D", price_root=tmp_path / "prices")
    assert rows[0].source == "cboe"
    assert rows[0].close == 13.5


def test_parse_eoddata_index_daily_html_reads_recent_rows() -> None:
    html = """
    <table>
      <tr><th>Date</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr>
      <tr><td>04 Sep 26</td><td>46.71</td><td>48.11</td><td>45.92</td><td>46.91</td><td>0</td></tr>
      <tr><td>03 Sep 26</td><td>49.30</td><td>51.49</td><td>46.52</td><td>50.89</td><td>0</td></tr>
    </table>
    """

    rows = parse_eoddata_index_daily_html(
        html,
        symbol="$S5FI",
        source_symbol="S5FI",
        start_date=date(2026, 9, 4),
        end_date=date(2026, 9, 4),
    )

    assert len(rows) == 1
    assert rows[0].source == "eoddata"
    assert rows[0].source_symbol == "S5FI"
    assert rows[0].symbol == "$S5FI"
    assert rows[0].observed_date == date(2026, 9, 4)
    assert rows[0].close == 46.91
    assert rows[0].adjusted_close == 46.91


def test_fetch_and_write_eoddata_index_daily_prices_uses_public_quote_page(
    tmp_path: Path,
) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            text=(
                "<table>"
                "<tr><th>Date</th><th>Open</th><th>High</th><th>Low</th>"
                "<th>Close</th><th>Volume</th></tr>"
                "<tr><td>04 Sep 26</td><td>68.00</td><td>69.00</td>"
                "<td>67.00</td><td>68.78</td><td>0</td></tr>"
                "</table>"
            ),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    results = fetch_and_write_eoddata_index_daily_prices(
        symbols=("$SPXA200R", "$S5TH"),
        start_date=date(2026, 9, 4),
        end_date=date(2026, 9, 4),
        output_root=tmp_path / "prices",
        client=client,
    )

    assert [result.symbol for result in results] == ["$S5TH"]
    assert results[0].source_symbol == "S5TH"
    assert results[0].observation_path.name == "INDEX_S5TH.jsonl"
    assert "stockquote/INDEX/S5TH.htm" in requested_urls[0]
    assert load_price_history(symbol="$S5TH", price_root=tmp_path / "prices")[0].close == 68.78


def test_fetch_and_write_yahoo_daily_prices_replaces_overlapping_vendor_rows(
    tmp_path: Path,
) -> None:
    frames = [
        pd.DataFrame(
            {
                "Open": [100.0],
                "High": [105.0],
                "Low": [99.0],
                "Close": [104.0],
                "Adj Close": [103.5],
                "Volume": [1_000_000],
            },
            index=pd.to_datetime(["2026-08-24"]),
        ),
        pd.DataFrame(
            {
                "Open": [100.0],
                "High": [106.0],
                "Low": [99.0],
                "Close": [105.0],
                "Adj Close": [104.5],
                "Volume": [1_100_000],
            },
            index=pd.to_datetime(["2026-08-24"]),
        ),
    ]
    for frame in frames:
        frame.index.name = "Date"

    def downloader(ticker, **kwargs):  # noqa: ANN001, ARG001
        return frames.pop(0)

    output_root = tmp_path / "prices"
    fetch_and_write_yahoo_daily_prices(
        symbols=("SPY",),
        start_date=date(2026, 8, 24),
        end_date=date(2026, 8, 24),
        output_root=output_root,
        downloader=downloader,
    )
    fetch_and_write_yahoo_daily_prices(
        symbols=("SPY",),
        start_date=date(2026, 8, 24),
        end_date=date(2026, 8, 24),
        output_root=output_root,
        downloader=downloader,
    )

    rows = load_price_history(symbol="SPY", price_root=output_root)
    assert len(rows) == 1
    assert rows[0].close == 105.0
    assert rows[0].adjusted_close == 104.5
    assert rows[0].volume == 1_100_000


def test_to_stooq_symbol_adds_us_suffix_only_when_needed() -> None:
    assert to_stooq_symbol("META") == "meta.us"
    assert to_stooq_symbol("BRK.B") == "brk.b.us"
    assert to_stooq_symbol("BMW.DE") == "bmw.de"
    assert to_stooq_symbol("^SPX") == "^spx"


def test_to_cboe_index_symbol_maps_volatility_index_aliases() -> None:
    assert to_cboe_index_symbol("^VIX") == "VIX"
    assert to_cboe_index_symbol("vix9d") == "VIX9D"
    assert to_cboe_index_symbol("^VIX3M") == "VIX3M"
    assert to_cboe_index_symbol("VVIX") == "VVIX"
    with pytest.raises(PriceDataError, match="Unsupported CBOE index symbol"):
        to_cboe_index_symbol("SPY")


def test_to_eoddata_index_symbol_maps_breadth_aliases() -> None:
    assert to_eoddata_index_symbol("$S5FI") == "S5FI"
    assert to_eoddata_index_symbol("$SPXA50R") == "S5FI"
    assert to_eoddata_index_symbol("$S5TH") == "S5TH"
    assert to_eoddata_index_symbol("$SPXA200R") == "S5TH"
    with pytest.raises(PriceDataError, match="Unsupported EODData index symbol"):
        to_eoddata_index_symbol("SPY")


def _price_row(*, close: float, symbol: str = "META") -> DailyPriceObservation:
    return DailyPriceObservation(
        source="fixture",
        source_symbol=symbol,
        symbol=symbol,
        observed_date=date(2026, 8, 24),
        open=100.0,
        high=105.0,
        low=99.0,
        close=close,
        volume=1_000_000,
        adjusted_close=close,
    )
