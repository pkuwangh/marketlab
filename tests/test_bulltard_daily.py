from collections.abc import Callable
from datetime import date
from pathlib import Path

import httpx

from marketlab.bulltard.daily import run_daily_workflow

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
