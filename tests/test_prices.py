from datetime import date
from pathlib import Path

import httpx
import pytest

from marketlab.prices import (
    PriceDataError,
    fetch_and_write_stooq_daily_prices,
    load_price_history,
    parse_stooq_daily_csv,
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


def test_to_stooq_symbol_adds_us_suffix_only_when_needed() -> None:
    assert to_stooq_symbol("META") == "meta.us"
    assert to_stooq_symbol("BRK.B") == "brk.b.us"
    assert to_stooq_symbol("BMW.DE") == "bmw.de"
    assert to_stooq_symbol("^SPX") == "^spx"
