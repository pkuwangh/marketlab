import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import httpx

from marketlab.bulltard.daily import refresh_candidate_prices, run_daily_workflow
from marketlab.prices import PriceDataError, PriceFetchResult

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bulltard"


def test_run_daily_workflow_ingests_ranked_interest_and_interest_ticker_details(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "observations" / "bulltard"
    debug_root = tmp_path / "debug" / "bulltard"
    requested_ticker_paths: list[str] = []
    client = httpx.Client(
        transport=httpx.MockTransport(_handler(requested_ticker_paths=requested_ticker_paths)),
        follow_redirects=True,
    )

    result = run_daily_workflow(
        source_date=date(2026, 8, 26),
        recap_path=FIXTURE_DIR / "recap_with_trades_of_interest.html",
        output_root=output_root,
        debug_root=debug_root,
        client=client,
    )

    assert result.ranked_result.row_count == 3
    assert result.trades_of_interest_result is not None
    assert result.trades_of_interest_result.symbols == ("META", "XAR")
    assert [ticker.fetched_page.symbol for ticker in result.ticker_results] == ["META", "XAR"]
    assert result.ticker_failures == ()
    assert requested_ticker_paths == ["/tickers/META", "/tickers/XAR"]
    assert (output_root / "ranked_option_trades" / "2026-08-26.jsonl").is_file()
    assert (output_root / "trades_of_interest" / "2026-08-26.jsonl").is_file()
    assert (output_root / "ticker_flow" / "META" / "2026-08-26.jsonl").is_file()
    assert "META" in result.candidate_table
    assert "interest#1" in result.candidate_table
    assert "detail" in result.candidate_table


def test_run_daily_workflow_can_add_top_ranked_details(tmp_path: Path) -> None:
    requested_ticker_paths: list[str] = []
    client = httpx.Client(
        transport=httpx.MockTransport(_handler(requested_ticker_paths=requested_ticker_paths)),
        follow_redirects=True,
    )

    result = run_daily_workflow(
        source_date=date(2026, 8, 26),
        recap_path=FIXTURE_DIR / "recap_with_trades_of_interest.html",
        output_root=tmp_path / "observations" / "bulltard",
        debug_root=tmp_path / "debug" / "bulltard",
        top_ranked=1,
        extra_tickers=("meta",),
        client=client,
    )

    assert [ticker.fetched_page.symbol for ticker in result.ticker_results] == [
        "META",
        "XAR",
        "INTC",
    ]
    assert requested_ticker_paths == ["/tickers/META", "/tickers/XAR", "/tickers/INTC"]


def test_run_daily_workflow_can_skip_ticker_details(tmp_path: Path) -> None:
    requested_ticker_paths: list[str] = []
    client = httpx.Client(
        transport=httpx.MockTransport(_handler(requested_ticker_paths=requested_ticker_paths)),
        follow_redirects=True,
    )

    result = run_daily_workflow(
        source_date=date(2026, 8, 26),
        recap_path=FIXTURE_DIR / "recap_with_trades_of_interest.html",
        output_root=tmp_path / "observations" / "bulltard",
        debug_root=tmp_path / "debug" / "bulltard",
        fetch_ticker_details=False,
        client=client,
    )

    assert result.ticker_results == ()
    assert requested_ticker_paths == []


def test_refresh_candidate_prices_fetches_candidates_and_benchmarks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    observations_root = tmp_path / "observations" / "bulltard"
    price_root = tmp_path / "prices"
    _write_jsonl(
        observations_root / "ranked_option_trades" / "2026-08-26.jsonl",
        [
            {
                "source_date": "2026-08-26",
                "symbol": "INTC",
                "side": "bullish",
                "score": 19.0,
                "trade_count": 31,
                "premium": 74508194.5,
            }
        ],
    )
    _write_jsonl(
        observations_root / "trades_of_interest" / "2026-08-26.jsonl",
        [
            {
                "source_date": "2026-08-26",
                "rank": 1,
                "symbol": "META",
                "note": "Recap interest note.",
            }
        ],
    )
    calls: list[str] = []

    def fake_fetch_and_write_yahoo_daily_prices(
        *,
        symbols: tuple[str, ...],
        start_date: date,
        end_date: date,
        output_root: Path,
        downloader,
    ) -> tuple[PriceFetchResult, ...]:
        assert start_date == date(2025, 1, 1)
        assert end_date == date(2026, 8, 27)
        assert output_root == price_root
        calls.extend(symbols)
        return tuple(
            PriceFetchResult(
                symbol=symbol,
                source_symbol=symbol,
                observation_path=price_root / f"{symbol}.jsonl",
                row_count=414,
            )
            for symbol in symbols
        )

    monkeypatch.setattr(
        "marketlab.bulltard.daily.fetch_and_write_yahoo_daily_prices",
        fake_fetch_and_write_yahoo_daily_prices,
    )

    result = refresh_candidate_prices(
        source_date=date(2026, 8, 26),
        start_date=date(2025, 1, 1),
        end_date=date(2026, 8, 27),
        observations_root=observations_root,
        price_root=price_root,
        limit=10,
    )

    assert result.requested_symbols == ("META", "INTC", "SPY", "QQQ")
    assert calls == ["META", "INTC", "SPY", "QQQ"]
    assert [price_result.symbol for price_result in result.price_results] == [
        "META",
        "INTC",
        "SPY",
        "QQQ",
    ]
    assert result.price_failures == ()


def test_refresh_candidate_prices_records_partial_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    observations_root = tmp_path / "observations" / "bulltard"
    price_root = tmp_path / "prices"
    _write_jsonl(
        observations_root / "ranked_option_trades" / "2026-08-26.jsonl",
        [
            {
                "source_date": "2026-08-26",
                "symbol": "GOOD",
                "side": "bullish",
                "score": 5.0,
                "trade_count": 1,
                "premium": 1000000.0,
            },
            {
                "source_date": "2026-08-26",
                "symbol": "BAD",
                "side": "bullish",
                "score": 4.0,
                "trade_count": 1,
                "premium": 900000.0,
            },
        ],
    )

    def fake_fetch_and_write_yahoo_daily_prices(
        *,
        symbols: tuple[str, ...],
        start_date: date,
        end_date: date,
        output_root: Path,
        downloader,
    ) -> tuple[PriceFetchResult, ...]:
        symbol = symbols[0]
        if symbol == "BAD":
            raise PriceDataError("fixture failure")
        return (
            PriceFetchResult(
                symbol=symbol,
                source_symbol=symbol,
                observation_path=price_root / f"{symbol}.jsonl",
                row_count=10,
            ),
        )

    monkeypatch.setattr(
        "marketlab.bulltard.daily.fetch_and_write_yahoo_daily_prices",
        fake_fetch_and_write_yahoo_daily_prices,
    )

    result = refresh_candidate_prices(
        source_date=date(2026, 8, 26),
        start_date=date(2025, 1, 1),
        end_date=date(2026, 8, 27),
        observations_root=observations_root,
        price_root=price_root,
        limit=10,
        extra_symbols=(),
    )

    assert [price_result.symbol for price_result in result.price_results] == ["GOOD"]
    assert len(result.price_failures) == 1
    assert result.price_failures[0].symbol == "BAD"
    assert result.price_failures[0].error == "fixture failure"


def _handler(
    *,
    requested_ticker_paths: list[str],
) -> Callable[[httpx.Request], httpx.Response]:
    ranked_html = (FIXTURE_DIR / "ranked_option_trades.html").read_bytes()
    ticker_html = (FIXTURE_DIR / "ticker_intc.html").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "jamesbulltard.substack.com":
            return httpx.Response(302, headers={"location": "https://app.jamesbulltard.com/"})
        if request.url.path == "/":
            return httpx.Response(
                200,
                headers={"set-cookie": "bulltard_session=fixture-session; Path=/"},
                content=b"<html>home</html>",
            )
        if request.url.path == "/ranked_option_trades":
            return httpx.Response(200, headers={"content-type": "text/html"}, content=ranked_html)
        if request.url.path.startswith("/tickers/"):
            requested_ticker_paths.append(request.url.path)
            return httpx.Response(200, headers={"content-type": "text/html"}, content=ticker_html)
        return httpx.Response(404)

    return handler


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
