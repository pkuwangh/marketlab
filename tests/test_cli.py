import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from marketlab import __version__
from marketlab.bulltard.ingest import (
    FetchedTickerPage,
    FetchedView,
    IngestResult,
    TickerIngestResult,
    TradesOfInterestIngestResult,
)
from marketlab.cli import app, bulltard_app

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bulltard"


def test_typer_app_has_no_args_is_help_enabled() -> None:
    assert app.info.no_args_is_help is True
    assert bulltard_app.info.no_args_is_help is True


def test_typer_no_args_shows_help_without_traceback() -> None:
    result = CliRunner().invoke(app, [])

    assert result.exit_code != 0
    assert "MarketLab research workflow CLI." in result.output
    assert "--version" in result.output
    assert "Traceback" not in result.output


def test_bulltard_no_args_shows_help_without_traceback() -> None:
    result = CliRunner().invoke(app, ["bulltard"])

    assert result.exit_code != 0
    assert "Bulltard link extraction and ingest utilities." in result.output
    assert "inspect-recap" in result.output
    assert "ingest" in result.output
    assert "Traceback" not in result.output


def test_inspect_recap_no_args_shows_help_without_missing_argument_error() -> None:
    result = CliRunner().invoke(app, ["bulltard", "inspect-recap"])

    assert result.exit_code != 0
    assert "Extract the signed Bulltard source URL" in result.output
    assert "recap_path" in result.output
    assert "Missing argument" not in result.output
    assert "Traceback" not in result.output


def test_ingest_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["bulltard", "ingest"])

    assert result.exit_code != 0
    assert "Retrieve and parse one targeted Bulltard view" in result.output
    assert "recap_path" in result.output
    assert "--date" in result.output
    assert "Missing option" not in result.output
    assert "Missing argument" not in result.output
    assert "Traceback" not in result.output


def test_ticker_no_args_shows_help_without_missing_argument_error() -> None:
    result = CliRunner().invoke(app, ["bulltard", "ticker"])

    assert result.exit_code != 0
    assert "Retrieve and parse one Bulltard ticker detail page" in result.output
    assert "symbol" in result.output
    assert "recap_path" in result.output
    assert "--date" in result.output
    assert "Missing argument" not in result.output
    assert "Traceback" not in result.output


def test_candidates_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["bulltard", "candidates"])

    assert result.exit_code != 0
    assert "Review Bulltard ranked candidates with available ticker flow" in result.output
    assert "--date" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_trades_of_interest_no_args_shows_help_without_missing_argument_error() -> None:
    result = CliRunner().invoke(app, ["bulltard", "trades-of-interest"])

    assert result.exit_code != 0
    assert "Parse recap Trades Of Interest into observations" in result.output
    assert "recap_path" in result.output
    assert "--date" in result.output
    assert "Missing argument" not in result.output
    assert "Traceback" not in result.output


def test_version_option() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert f"marketlab {__version__}" in result.output


def test_bulltard_inspect_recap_outputs_full_signed_url_by_default() -> None:
    result = CliRunner().invoke(app, ["bulltard", "inspect-recap", str(FIXTURE_DIR / "recap.html")])

    assert result.exit_code == 0
    assert "jamesbulltard.substack.com/redirect" in result.output
    assert "fixture-secret" in result.output


def test_bulltard_inspect_recap_unwraps_gmail_tracking_redirect() -> None:
    result = CliRunner().invoke(
        app,
        ["bulltard", "inspect-recap", str(FIXTURE_DIR / "gmail_wrapped_database_link.html")],
    )

    assert result.exit_code == 0
    assert (
        "https://substack.com/redirect/00000000-0000-4000-8000-000000000000?j=fixture-jwt"
        in result.output
    )
    assert "google.com/url" not in result.output


def test_bulltard_ingest_retrieves_first_view(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "observations" / "bulltard"
    debug_root = tmp_path / "debug" / "bulltard"

    def fake_ingest_planned_view(plan, *, debug_root: Path) -> IngestResult:  # noqa: ANN001
        fetched_view = FetchedView(
            plan=plan,
            final_url="https://app.jamesbulltard.com/ranked_option_trades",
            status_code=200,
            content_type="text/html",
            byte_count=42,
            debug_path=debug_root / plan.view.output_slug / f"{plan.source_date.isoformat()}.html",
        )
        return IngestResult(
            fetched_view=fetched_view,
            row_count=3,
            observation_path=plan.observation_path,
        )

    monkeypatch.setattr("marketlab.cli.ingest_planned_view", fake_ingest_planned_view)

    result = CliRunner().invoke(
        app,
        [
            "bulltard",
            "ingest",
            str(FIXTURE_DIR / "recap.html"),
            "--date",
            "2026-08-24",
            "--output-root",
            str(output_root),
            "--debug-root",
            str(debug_root),
        ],
    )

    assert result.exit_code == 0
    assert "view=ranked-option-trades" in result.output
    assert "route_path=/ranked_option_trades" in result.output
    assert "jamesbulltard.substack.com/redirect" in result.output
    assert "fixture-secret" in result.output
    assert "final_url=https://app.jamesbulltard.com/ranked_option_trades" in result.output
    assert "status_code=200" in result.output
    assert "byte_count=42" in result.output
    assert str(debug_root / "ranked_option_trades" / "2026-08-24.html") in result.output
    assert (
        f"observation_path={output_root / 'ranked_option_trades' / '2026-08-24.jsonl'}"
        in result.output
    )
    assert "row_count=3" in result.output


def test_bulltard_ticker_fetches_detail_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "observations" / "bulltard"
    debug_root = tmp_path / "debug" / "bulltard"

    def fake_ingest_ticker_page(
        *,
        source_date,
        symbol: str,
        recap_path: Path,
        output_root: Path,
        debug_root: Path,
    ) -> TickerIngestResult:
        fetched_page = FetchedTickerPage(
            source_date=source_date,
            symbol=symbol.upper(),
            signed_url="https://jamesbulltard.substack.com/redirect?token=fixture-secret",
            final_url=f"https://app.jamesbulltard.com/tickers/{symbol.upper()}",
            status_code=200,
            content_type="text/html",
            byte_count=123,
            debug_path=debug_root / "tickers" / symbol.upper() / f"{source_date.isoformat()}.html",
        )
        return TickerIngestResult(
            fetched_page=fetched_page,
            row_count=3,
            observation_path=output_root / "ticker_flow" / symbol.upper() / "2026-08-25.jsonl",
        )

    monkeypatch.setattr("marketlab.cli.ingest_ticker_page", fake_ingest_ticker_page)

    result = CliRunner().invoke(
        app,
        [
            "bulltard",
            "ticker",
            "intc",
            str(FIXTURE_DIR / "recap.html"),
            "--date",
            "2026-08-25",
            "--output-root",
            str(output_root),
            "--debug-root",
            str(debug_root),
        ],
    )

    assert result.exit_code == 0
    assert "symbol=INTC" in result.output
    assert "fixture-secret" in result.output
    assert "final_url=https://app.jamesbulltard.com/tickers/INTC" in result.output
    assert "status_code=200" in result.output
    assert "byte_count=123" in result.output
    assert str(debug_root / "tickers" / "INTC" / "2026-08-25.html") in result.output
    assert str(output_root / "ticker_flow" / "INTC" / "2026-08-25.jsonl") in result.output
    assert "row_count=3" in result.output


def test_bulltard_candidates_outputs_review_table(tmp_path: Path) -> None:
    observations_root = tmp_path / "observations" / "bulltard"
    ranked_path = observations_root / "ranked_option_trades" / "2026-08-26.jsonl"
    ticker_flow_path = observations_root / "ticker_flow" / "INTC" / "2026-08-26.jsonl"
    _write_jsonl(
        ranked_path,
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
        ticker_flow_path,
        [
            {
                "symbol": "INTC",
                "traded_at": "2026-08-26T10:15",
                "order_type": "Puts Sold",
                "contract": "100P",
                "expiry": "2027-06-17",
                "premium": 2650000.0,
            }
        ],
    )

    result = CliRunner().invoke(
        app,
        [
            "bulltard",
            "candidates",
            "--date",
            "2026-08-26",
            "--observations-root",
            str(observations_root),
        ],
    )

    assert result.exit_code == 0
    assert "symbol" in result.output
    assert "INTC" in result.output
    assert "$74.5M" in result.output
    assert "Puts Sold 100P" in result.output


def test_bulltard_trades_of_interest_writes_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "observations" / "bulltard"

    def fake_ingest_trades_of_interest(
        *,
        source_date,
        recap_path: Path,
        output_root: Path,
    ) -> TradesOfInterestIngestResult:
        return TradesOfInterestIngestResult(
            source_date=source_date,
            recap_path=recap_path,
            row_count=2,
            observation_path=output_root / "trades_of_interest" / "2026-08-26.jsonl",
            symbols=("META", "XAR"),
        )

    monkeypatch.setattr("marketlab.cli.ingest_trades_of_interest", fake_ingest_trades_of_interest)

    result = CliRunner().invoke(
        app,
        [
            "bulltard",
            "trades-of-interest",
            str(FIXTURE_DIR / "trades_of_interest.html"),
            "--date",
            "2026-08-26",
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0
    assert str(output_root / "trades_of_interest" / "2026-08-26.jsonl") in result.output
    assert "row_count=2" in result.output
    assert "symbols=META,XAR" in result.output


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
