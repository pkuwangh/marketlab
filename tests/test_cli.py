import json
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from marketlab import __version__
from marketlab.bulltard.daily import (
    CandidatePriceRefreshResult,
    DailyWorkflowResult,
    PriceRefreshFailure,
)
from marketlab.bulltard.ingest import (
    FetchedTickerPage,
    FetchedView,
    IngestResult,
    TickerIngestResult,
    TradesOfInterestIngestResult,
)
from marketlab.bulltard.models import BulltardView, IngestPlan
from marketlab.bulltard.outcomes import (
    CandidateOutcomeResult,
    ForwardOutcome,
    OutcomeSummaryRow,
)
from marketlab.bulltard.validation import (
    CandidateValidationResult,
    CandidateValidationSnapshot,
    CandidateValidationSummary,
)
from marketlab.cli import app, bulltard_app, prices_app, regime_app
from marketlab.prices import PriceFetchResult
from marketlab.regime import (
    RegimeComponentScore,
    RegimeForwardOutcome,
    RegimeOutcomeResult,
    RegimeOutcomeSummaryRow,
    RegimePriceRefreshResult,
    RegimeSnapshot,
    RegimeSnapshotResult,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bulltard"


def test_typer_app_has_no_args_is_help_enabled() -> None:
    assert app.info.no_args_is_help is True
    assert bulltard_app.info.no_args_is_help is True
    assert prices_app.info.no_args_is_help is True
    assert regime_app.info.no_args_is_help is True


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


def test_prices_no_args_shows_help_without_traceback() -> None:
    result = CliRunner().invoke(app, ["prices"])

    assert result.exit_code != 0
    assert "Daily OHLCV price utilities." in result.output
    assert "fetch" in result.output
    assert "Traceback" not in result.output


def test_regime_no_args_shows_help_without_traceback() -> None:
    result = CliRunner().invoke(app, ["regime"])

    assert result.exit_code != 0
    assert "Market regime utilities." in result.output
    assert "snapshot" in result.output
    assert "Traceback" not in result.output


def test_prices_fetch_no_args_shows_help_without_missing_argument_error() -> None:
    result = CliRunner().invoke(app, ["prices", "fetch"])

    assert result.exit_code != 0
    assert "Fetch daily OHLCV observations." in result.output
    assert "SYMBOL[,SYMBOL...]" in result.output
    assert "--start" in result.output
    assert "Missing argument" not in result.output
    assert "Traceback" not in result.output


def test_prices_fetch_yahoo_no_args_shows_help_without_missing_argument_error() -> None:
    result = CliRunner().invoke(app, ["prices", "fetch-yahoo"])

    assert result.exit_code != 0
    assert "Fetch daily OHLCV observations from Yahoo Finance" in result.output
    assert "SYMBOL[,SYMBOL...]" in result.output
    assert "--start" in result.output
    assert "Missing argument" not in result.output
    assert "Traceback" not in result.output


def test_regime_snapshot_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["regime", "snapshot"])

    assert result.exit_code != 0
    assert "Compute a market regime snapshot" in result.output
    assert "--date" in result.output
    assert "--fetch-prices" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_regime_outcomes_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["regime", "outcomes"])

    assert result.exit_code != 0
    assert "Replay forward SPY/QQQ outcomes" in result.output
    assert "--start" in result.output
    assert "--end" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_prices_import_csv_no_args_shows_help_without_missing_argument_error() -> None:
    result = CliRunner().invoke(app, ["prices", "import-csv"])

    assert result.exit_code != 0
    assert "Import daily OHLCV observations" in result.output
    assert "symbol" in result.output
    assert "csv_path" in result.output
    assert "Missing argument" not in result.output
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


def test_validate_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["bulltard", "validate"])

    assert result.exit_code != 0
    assert "Validate Bulltard candidates" in result.output
    assert "--date" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_refresh_prices_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["bulltard", "refresh-prices"])

    assert result.exit_code != 0
    assert "Refresh Yahoo prices for captured Bulltard candidates" in result.output
    assert "--date" in result.output
    assert "--start" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_outcomes_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["bulltard", "outcomes"])

    assert result.exit_code != 0
    assert "Replay forward outcomes" in result.output
    assert "--start" in result.output
    assert "--end" in result.output
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


def test_daily_no_args_shows_help_without_missing_argument_error() -> None:
    result = CliRunner().invoke(app, ["bulltard", "daily"])

    assert result.exit_code != 0
    assert "Run the daily Bulltard candidate workflow" in result.output
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


def test_bulltard_daily_runs_candidate_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "observations" / "bulltard"
    debug_root = tmp_path / "debug" / "bulltard"

    def fake_run_daily_workflow(
        *,
        source_date,
        recap_path: Path,
        output_root: Path,
        debug_root: Path,
        fetch_ticker_details: bool,
        top_ranked: int,
        extra_tickers: tuple[str, ...],
        limit: int,
    ) -> DailyWorkflowResult:
        assert source_date == date(2026, 8, 26)
        assert fetch_ticker_details is True
        assert top_ranked == 1
        assert extra_tickers == ("INTC", "META")
        assert limit == 12
        plan = IngestPlan(
            source_date=source_date,
            view=BulltardView.RANKED_OPTION_TRADES,
            recap_path=recap_path,
            signed_url="https://jamesbulltard.substack.com/redirect?token=fixture-secret",
            observation_path=output_root / "ranked_option_trades" / "2026-08-26.jsonl",
        )
        ranked_result = IngestResult(
            fetched_view=FetchedView(
                plan=plan,
                final_url="https://app.jamesbulltard.com/ranked_option_trades",
                status_code=200,
                content_type="text/html",
                byte_count=42,
                debug_path=debug_root / "ranked_option_trades" / "2026-08-26.html",
            ),
            row_count=40,
            observation_path=plan.observation_path,
        )
        interest_result = TradesOfInterestIngestResult(
            source_date=source_date,
            recap_path=recap_path,
            row_count=2,
            observation_path=output_root / "trades_of_interest" / "2026-08-26.jsonl",
            symbols=("META", "XAR"),
        )
        return DailyWorkflowResult(
            source_date=source_date,
            ranked_result=ranked_result,
            trades_of_interest_result=interest_result,
            ticker_results=(),
            ticker_failures=(),
            candidate_table="symbol  source\nMETA    ranked+interest#1",
        )

    monkeypatch.setattr("marketlab.cli.run_daily_workflow", fake_run_daily_workflow)

    result = CliRunner().invoke(
        app,
        [
            "bulltard",
            "daily",
            str(FIXTURE_DIR / "recap_with_trades_of_interest.html"),
            "--date",
            "2026-08-26",
            "--output-root",
            str(output_root),
            "--debug-root",
            str(debug_root),
            "--top-ranked",
            "1",
            "--ticker",
            "INTC,META",
        ],
    )

    assert result.exit_code == 0
    assert (
        f"ranked_observation_path={output_root / 'ranked_option_trades' / '2026-08-26.jsonl'}"
        in result.output
    )
    assert "ranked_row_count=40" in result.output
    assert (
        f"trades_of_interest_path={output_root / 'trades_of_interest' / '2026-08-26.jsonl'}"
        in result.output
    )
    assert "trades_of_interest_symbols=META,XAR" in result.output
    assert "ticker_detail_symbols=" in result.output
    assert "META    ranked+interest#1" in result.output


def test_prices_fetch_outputs_written_observation_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "prices"

    def fake_fetch_and_write_stooq_daily_prices(
        *,
        symbols: tuple[str, ...],
        start_date: date,
        end_date: date,
        output_root: Path,
        api_key: str | None,
    ) -> tuple[PriceFetchResult, ...]:
        assert symbols == ("META", "SPY")
        assert start_date == date(2026, 1, 1)
        assert end_date == date(2026, 8, 26)
        assert api_key == "fixture-key"
        return (
            PriceFetchResult(
                symbol="META",
                source_symbol="meta.us",
                observation_path=output_root / "META.jsonl",
                row_count=100,
            ),
        )

    monkeypatch.setattr(
        "marketlab.cli.fetch_and_write_stooq_daily_prices",
        fake_fetch_and_write_stooq_daily_prices,
    )

    result = CliRunner().invoke(
        app,
        [
            "prices",
            "fetch",
            "META,SPY",
            "--start",
            "2026-01-01",
            "--end",
            "2026-08-26",
            "--output-root",
            str(output_root),
            "--stooq-api-key",
            "fixture-key",
        ],
    )

    assert result.exit_code == 0
    assert "symbol=META source_symbol=meta.us row_count=100" in result.output
    assert str(output_root / "META.jsonl") in result.output


def test_prices_fetch_yahoo_outputs_written_observation_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "prices"

    def fake_fetch_and_write_yahoo_daily_prices(
        *,
        symbols: tuple[str, ...],
        start_date: date,
        end_date: date,
        output_root: Path,
    ) -> tuple[PriceFetchResult, ...]:
        assert symbols == ("META", "SPY")
        assert start_date == date(2026, 1, 1)
        assert end_date == date(2026, 8, 27)
        return (
            PriceFetchResult(
                symbol="META",
                source_symbol="META",
                observation_path=output_root / "META.jsonl",
                row_count=420,
            ),
        )

    monkeypatch.setattr(
        "marketlab.cli.fetch_and_write_yahoo_daily_prices",
        fake_fetch_and_write_yahoo_daily_prices,
    )

    result = CliRunner().invoke(
        app,
        [
            "prices",
            "fetch-yahoo",
            "META,SPY",
            "--start",
            "2026-01-01",
            "--end",
            "2026-08-27",
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0
    assert "symbol=META source_symbol=META row_count=420" in result.output
    assert str(output_root / "META.jsonl") in result.output


def test_prices_import_csv_outputs_written_observation_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "prices"
    csv_path = tmp_path / "META.csv"
    csv_path.write_text("Date,Open,High,Low,Close,Volume\n", encoding="utf-8")

    def fake_import_daily_price_csv(
        *,
        symbol: str,
        csv_path: Path,
        output_root: Path,
        source: str,
        source_symbol: str | None,
    ) -> PriceFetchResult:
        assert symbol == "META"
        assert csv_path == csv_path_arg
        assert source == "manual"
        assert source_symbol == "meta.us"
        return PriceFetchResult(
            symbol="META",
            source_symbol="meta.us",
            observation_path=output_root / "META.jsonl",
            row_count=2,
        )

    csv_path_arg = csv_path
    monkeypatch.setattr("marketlab.cli.import_daily_price_csv", fake_import_daily_price_csv)

    result = CliRunner().invoke(
        app,
        [
            "prices",
            "import-csv",
            "META",
            str(csv_path),
            "--output-root",
            str(output_root),
            "--source",
            "manual",
            "--source-symbol",
            "meta.us",
        ],
    )

    assert result.exit_code == 0
    assert "symbol=META source_symbol=meta.us row_count=2" in result.output
    assert str(output_root / "META.jsonl") in result.output


def test_regime_snapshot_fetches_prices_and_outputs_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    price_root = tmp_path / "prices"
    snapshot_root = tmp_path / "regime"
    events: list[str] = []

    def fake_refresh_regime_prices(
        *,
        start_date: date,
        end_date: date,
        price_root: Path,
    ) -> RegimePriceRefreshResult:
        assert start_date == date(2025, 1, 1)
        assert end_date == date(2026, 8, 28)
        assert price_root == price_root_arg
        events.append("prices")
        return RegimePriceRefreshResult(
            start_date=start_date,
            end_date=end_date,
            requested_symbols=("SPY", "QQQ"),
            price_results=(
                PriceFetchResult(
                    symbol="SPY",
                    source_symbol="SPY",
                    observation_path=price_root / "SPY.jsonl",
                    row_count=420,
                ),
            ),
            price_failures=(),
        )

    def fake_compute_regime_snapshot(
        *,
        source_date: date,
        price_root: Path,
        snapshot_root: Path,
        write_snapshot: bool,
    ) -> RegimeSnapshotResult:
        assert events == ["prices"]
        assert source_date == date(2026, 8, 28)
        assert price_root == price_root_arg
        assert snapshot_root == snapshot_root_arg
        assert write_snapshot is True
        events.append("snapshot")
        snapshot = _regime_snapshot(source_date=source_date)
        return RegimeSnapshotResult(
            source_date=source_date,
            snapshot=snapshot,
            snapshot_path=snapshot_root / "2026-08-28.json",
            table="component  score  status\ntrend     +2     constructive",
        )

    price_root_arg = price_root
    snapshot_root_arg = snapshot_root
    monkeypatch.setattr("marketlab.cli.refresh_regime_prices", fake_refresh_regime_prices)
    monkeypatch.setattr("marketlab.cli.compute_regime_snapshot", fake_compute_regime_snapshot)

    result = CliRunner().invoke(
        app,
        [
            "regime",
            "snapshot",
            "--date",
            "2026-08-28",
            "--fetch-prices",
            "--price-start",
            "2025-01-01",
            "--price-end",
            "2026-08-28",
            "--price-root",
            str(price_root),
            "--snapshot-root",
            str(snapshot_root),
        ],
    )

    assert result.exit_code == 0
    assert events == ["prices", "snapshot"]
    assert "regime_price_symbols=SPY,QQQ" in result.output
    assert "regime_price_success_count=1" in result.output
    assert f"regime_snapshot_path={snapshot_root / '2026-08-28.json'}" in result.output
    assert "regime_date=2026-08-28" in result.output
    assert "regime=risk_on" in result.output
    assert "regime_score=5" in result.output
    assert "trend     +2     constructive" in result.output


def test_regime_outcomes_outputs_summary_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_root = tmp_path / "regime"
    price_root = tmp_path / "prices"

    def fake_compute_regime_outcomes(
        *,
        start_date: date,
        end_date: date,
        snapshot_root: Path,
        price_root: Path,
        horizons: tuple[int, ...],
    ) -> RegimeOutcomeResult:
        assert start_date == date(2026, 1, 1)
        assert end_date == date(2026, 8, 28)
        assert snapshot_root == snapshot_root_arg
        assert price_root == price_root_arg
        assert horizons == (20, 65)
        return RegimeOutcomeResult(
            start_date=start_date,
            end_date=end_date,
            outcomes=(
                RegimeForwardOutcome(
                    source_date=date(2026, 8, 1),
                    price_date=date(2026, 8, 1),
                    regime="risk_on",
                    score=5,
                    confidence="high",
                    horizon_days=20,
                    spy_return=0.05,
                    qqq_return=0.08,
                    spy_max_drawdown=-0.02,
                    qqq_max_drawdown=-0.03,
                ),
            ),
            summary_rows=(
                RegimeOutcomeSummaryRow(
                    bucket="regime:risk_on",
                    horizon_days=20,
                    snapshot_count=1,
                    available_count=1,
                    avg_spy_return=0.05,
                    avg_qqq_return=0.08,
                    avg_spy_max_drawdown=-0.02,
                    avg_qqq_max_drawdown=-0.03,
                ),
            ),
            table="bucket          horizon\nregime:risk_on  20d",
        )

    snapshot_root_arg = snapshot_root
    price_root_arg = price_root
    monkeypatch.setattr("marketlab.cli.compute_regime_outcomes", fake_compute_regime_outcomes)

    result = CliRunner().invoke(
        app,
        [
            "regime",
            "outcomes",
            "--start",
            "2026-01-01",
            "--end",
            "2026-08-28",
            "--snapshot-root",
            str(snapshot_root),
            "--price-root",
            str(price_root),
            "--horizons",
            "20,65",
        ],
    )

    assert result.exit_code == 0
    assert "regime_outcome_count=1" in result.output
    assert "available_regime_outcome_count=1" in result.output
    assert "regime:risk_on  20d" in result.output


def test_bulltard_validate_outputs_snapshot_and_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations_root = tmp_path / "observations" / "bulltard"
    price_root = tmp_path / "prices"
    snapshot_root = tmp_path / "snapshots"

    def fake_validate_bulltard_candidates(
        *,
        source_date: date,
        observations_root: Path,
        price_root: Path,
        snapshot_root: Path,
        limit: int,
        min_dollar_volume: float,
        write_snapshot: bool,
    ) -> CandidateValidationResult:
        assert source_date == date(2026, 8, 26)
        assert limit == 5
        assert min_dollar_volume == 10_000_000.0
        assert write_snapshot is True
        return CandidateValidationResult(
            source_date=source_date,
            snapshots=(_candidate_snapshot(source_date=source_date, symbol="META"),),
            summary=_candidate_validation_summary(candidate_count=1, confirm_count=1),
            snapshot_path=snapshot_root / "2026-08-26.jsonl",
            table="symbol  status\nMETA    confirm",
        )

    monkeypatch.setattr(
        "marketlab.cli.validate_bulltard_candidates",
        fake_validate_bulltard_candidates,
    )

    result = CliRunner().invoke(
        app,
        [
            "bulltard",
            "validate",
            "--date",
            "2026-08-26",
            "--observations-root",
            str(observations_root),
            "--price-root",
            str(price_root),
            "--snapshot-root",
            str(snapshot_root),
            "--limit",
            "5",
            "--min-dollar-volume",
            "10000000",
        ],
    )

    assert result.exit_code == 0
    assert f"snapshot_path={snapshot_root / '2026-08-26.jsonl'}" in result.output
    assert "candidate_count=1" in result.output
    assert "validation_summary=candidates:1 confirm:1 watch:0 avoid:0" in result.output
    assert "META    confirm" in result.output


def test_bulltard_refresh_prices_outputs_successes_and_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations_root = tmp_path / "observations" / "bulltard"
    price_root = tmp_path / "prices"

    def fake_refresh_candidate_price_set(
        *,
        source_date: date,
        start_date: date,
        end_date: date,
        observations_root: Path,
        price_root: Path,
        limit: int,
    ) -> CandidatePriceRefreshResult:
        assert source_date == date(2026, 8, 26)
        assert start_date == date(2025, 1, 1)
        assert end_date == date(2026, 8, 28)
        assert limit == 12
        return CandidatePriceRefreshResult(
            source_date=source_date,
            start_date=start_date,
            end_date=end_date,
            requested_symbols=("META", "SPY"),
            price_results=(
                PriceFetchResult(
                    symbol="META",
                    source_symbol="META",
                    observation_path=price_root / "META.jsonl",
                    row_count=420,
                ),
            ),
            price_failures=(PriceRefreshFailure(symbol="SPY", error="fixture failure"),),
        )

    monkeypatch.setattr(
        "marketlab.cli.refresh_candidate_price_set", fake_refresh_candidate_price_set
    )

    result = CliRunner().invoke(
        app,
        [
            "bulltard",
            "refresh-prices",
            "--date",
            "2026-08-26",
            "--start",
            "2025-01-01",
            "--end",
            "2026-08-28",
            "--observations-root",
            str(observations_root),
            "--price-root",
            str(price_root),
        ],
    )

    assert result.exit_code == 0
    assert "price_symbols=META,SPY" in result.output
    assert "price_success_count=1" in result.output
    assert "price_failure_count=1" in result.output
    assert (
        f"price_result=META row_count=420 observation_path={price_root / 'META.jsonl'}"
        in result.output
    )
    assert "price_failure=SPY error=fixture failure" in result.output


def test_bulltard_outcomes_outputs_summary_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_root = tmp_path / "snapshots"
    price_root = tmp_path / "prices"

    def fake_compute_bulltard_outcomes(
        *,
        start_date: date,
        end_date: date,
        snapshot_root: Path,
        price_root: Path,
        horizons: tuple[int, ...],
    ) -> CandidateOutcomeResult:
        assert start_date == date(2026, 1, 1)
        assert end_date == date(2026, 8, 26)
        assert horizons == (20, 65)
        return CandidateOutcomeResult(
            start_date=start_date,
            end_date=end_date,
            outcomes=(
                ForwardOutcome(
                    source_date=start_date,
                    symbol="META",
                    bulltard_source="ranked+interest#1",
                    source_bucket="ranked+interest",
                    validation_status="confirm",
                    detail_bucket="with_detail",
                    horizon_days=20,
                    return_value=0.1,
                    relative_strength_spy=0.05,
                    max_drawdown=-0.03,
                ),
            ),
            summary_rows=(
                OutcomeSummaryRow(
                    cohort="all",
                    horizon_days=20,
                    candidate_count=1,
                    available_count=1,
                    avg_return=0.1,
                    hit_rate=1.0,
                    avg_relative_strength_spy=0.05,
                    avg_max_drawdown=-0.03,
                ),
            ),
            table="cohort  horizon\nall     20d",
        )

    monkeypatch.setattr("marketlab.cli.compute_bulltard_outcomes", fake_compute_bulltard_outcomes)

    result = CliRunner().invoke(
        app,
        [
            "bulltard",
            "outcomes",
            "--start",
            "2026-01-01",
            "--end",
            "2026-08-26",
            "--snapshot-root",
            str(snapshot_root),
            "--price-root",
            str(price_root),
            "--horizons",
            "20,65",
        ],
    )

    assert result.exit_code == 0
    assert "outcome_count=1" in result.output
    assert "available_outcome_count=1" in result.output
    assert "all     20d" in result.output


def test_bulltard_outcomes_defaults_to_short_and_swing_horizons(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_root = tmp_path / "snapshots"
    price_root = tmp_path / "prices"

    def fake_compute_bulltard_outcomes(
        *,
        start_date: date,
        end_date: date,
        snapshot_root: Path,
        price_root: Path,
        horizons: tuple[int, ...],
    ) -> CandidateOutcomeResult:
        assert horizons == (1, 5, 20, 40, 65, 126)
        return CandidateOutcomeResult(
            start_date=start_date,
            end_date=end_date,
            outcomes=(),
            summary_rows=(),
            table="No outcome rows found.",
        )

    monkeypatch.setattr("marketlab.cli.compute_bulltard_outcomes", fake_compute_bulltard_outcomes)

    result = CliRunner().invoke(
        app,
        [
            "bulltard",
            "outcomes",
            "--start",
            "2026-08-01",
            "--end",
            "2026-08-26",
            "--snapshot-root",
            str(snapshot_root),
            "--price-root",
            str(price_root),
        ],
    )

    assert result.exit_code == 0
    assert "outcome_count=0" in result.output
    assert "available_outcome_count=0" in result.output


def test_bulltard_daily_can_refresh_prices_validate_and_compute_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "observations" / "bulltard"
    debug_root = tmp_path / "debug" / "bulltard"
    price_root = tmp_path / "prices"
    snapshot_root = tmp_path / "snapshots"
    regime_snapshot_root = tmp_path / "regime"
    events: list[str] = []

    def fake_run_daily_workflow(
        *,
        source_date,
        recap_path: Path,
        output_root: Path,
        debug_root: Path,
        fetch_ticker_details: bool,
        top_ranked: int,
        extra_tickers: tuple[str, ...],
        limit: int,
    ) -> DailyWorkflowResult:
        events.append("capture")
        plan = IngestPlan(
            source_date=source_date,
            view=BulltardView.RANKED_OPTION_TRADES,
            recap_path=recap_path,
            signed_url="https://jamesbulltard.substack.com/redirect?token=fixture-secret",
            observation_path=output_root / "ranked_option_trades" / "2026-08-26.jsonl",
        )
        return DailyWorkflowResult(
            source_date=source_date,
            ranked_result=IngestResult(
                fetched_view=FetchedView(
                    plan=plan,
                    final_url="https://app.jamesbulltard.com/ranked_option_trades",
                    status_code=200,
                    content_type="text/html",
                    byte_count=42,
                    debug_path=debug_root / "ranked_option_trades" / "2026-08-26.html",
                ),
                row_count=40,
                observation_path=plan.observation_path,
            ),
            trades_of_interest_result=None,
            ticker_results=(),
            ticker_failures=(),
            candidate_table="symbol  source\nMETA    ranked",
        )

    def fake_refresh_candidate_price_set(
        *,
        source_date: date,
        start_date: date,
        end_date: date,
        observations_root: Path,
        price_root: Path,
        limit: int,
    ) -> CandidatePriceRefreshResult:
        assert events == ["capture"]
        assert source_date == date(2026, 8, 26)
        assert start_date == date(2025, 1, 1)
        assert end_date == date(2026, 8, 28)
        assert observations_root == output_root
        assert price_root == price_root_arg
        assert limit == 12
        events.append("candidate_prices")
        return CandidatePriceRefreshResult(
            source_date=source_date,
            start_date=start_date,
            end_date=end_date,
            requested_symbols=("META", "SPY"),
            price_results=(
                PriceFetchResult(
                    symbol="META",
                    source_symbol="META",
                    observation_path=price_root / "META.jsonl",
                    row_count=420,
                ),
                PriceFetchResult(
                    symbol="SPY",
                    source_symbol="SPY",
                    observation_path=price_root / "SPY.jsonl",
                    row_count=420,
                ),
            ),
            price_failures=(),
        )

    def fake_refresh_regime_prices(
        *,
        start_date: date,
        end_date: date,
        price_root: Path,
        symbols: tuple[str, ...],
    ) -> RegimePriceRefreshResult:
        assert events == ["capture", "candidate_prices"]
        assert start_date == date(2025, 1, 1)
        assert end_date == date(2026, 8, 28)
        assert price_root == price_root_arg
        assert symbols == ("IWM", "RSP", "HYG", "TLT", "^VIX")
        events.append("regime_prices")
        return RegimePriceRefreshResult(
            start_date=start_date,
            end_date=end_date,
            requested_symbols=symbols,
            price_results=(
                PriceFetchResult(
                    symbol="IWM",
                    source_symbol="IWM",
                    observation_path=price_root / "IWM.jsonl",
                    row_count=420,
                ),
            ),
            price_failures=(),
        )

    def fake_compute_regime_snapshot(
        *,
        source_date: date,
        price_root: Path,
        snapshot_root: Path,
        write_snapshot: bool,
    ) -> RegimeSnapshotResult:
        assert events == ["capture", "candidate_prices", "regime_prices"]
        assert source_date == date(2026, 8, 26)
        assert price_root == price_root_arg
        assert snapshot_root == regime_snapshot_root_arg
        assert write_snapshot is True
        events.append("regime_snapshot")
        return RegimeSnapshotResult(
            source_date=source_date,
            snapshot=_regime_snapshot(source_date=source_date),
            snapshot_path=snapshot_root / "2026-08-26.json",
            table="component  score  status\ntrend     +2     constructive",
        )

    def fake_validate_bulltard_candidates(
        *,
        source_date: date,
        observations_root: Path,
        price_root: Path,
        snapshot_root: Path,
        limit: int,
        min_dollar_volume: float,
        write_snapshot: bool,
    ) -> CandidateValidationResult:
        assert events == [
            "capture",
            "candidate_prices",
            "regime_prices",
            "regime_snapshot",
        ]
        assert observations_root == output_root
        assert price_root == price_root_arg
        assert snapshot_root == snapshot_root_arg
        assert limit == 12
        assert write_snapshot is True
        events.append("validate")
        return CandidateValidationResult(
            source_date=source_date,
            snapshots=(_candidate_snapshot(source_date=source_date, symbol="META"),),
            summary=_candidate_validation_summary(candidate_count=1, confirm_count=1),
            snapshot_path=snapshot_root / "2026-08-26.jsonl",
            table="symbol  status\nMETA    confirm",
        )

    def fake_compute_bulltard_outcomes(
        *,
        start_date: date,
        end_date: date,
        snapshot_root: Path,
        price_root: Path,
        horizons: tuple[int, ...],
    ) -> CandidateOutcomeResult:
        assert events == [
            "capture",
            "candidate_prices",
            "regime_prices",
            "regime_snapshot",
            "validate",
        ]
        assert start_date == date(2026, 8, 1)
        assert end_date == date(2026, 8, 26)
        assert snapshot_root == snapshot_root_arg
        assert price_root == price_root_arg
        assert horizons == (1, 5, 20)
        events.append("candidate_outcomes")
        return CandidateOutcomeResult(
            start_date=start_date,
            end_date=end_date,
            outcomes=(
                ForwardOutcome(
                    source_date=date(2026, 8, 26),
                    symbol="META",
                    bulltard_source="ranked",
                    source_bucket="ranked",
                    validation_status="confirm",
                    detail_bucket="with_detail",
                    horizon_days=1,
                    return_value=0.01,
                    relative_strength_spy=0.005,
                    max_drawdown=-0.01,
                ),
            ),
            summary_rows=(
                OutcomeSummaryRow(
                    cohort="all",
                    horizon_days=1,
                    candidate_count=1,
                    available_count=1,
                    avg_return=0.01,
                    hit_rate=1.0,
                    avg_relative_strength_spy=0.005,
                    avg_max_drawdown=-0.01,
                ),
            ),
            table="cohort  horizon\nall     1d",
        )

    def fake_compute_regime_outcomes(
        *,
        start_date: date,
        end_date: date,
        snapshot_root: Path,
        price_root: Path,
        horizons: tuple[int, ...],
    ) -> RegimeOutcomeResult:
        assert events == [
            "capture",
            "candidate_prices",
            "regime_prices",
            "regime_snapshot",
            "validate",
            "candidate_outcomes",
        ]
        assert start_date == date(2026, 8, 1)
        assert end_date == date(2026, 8, 26)
        assert snapshot_root == regime_snapshot_root_arg
        assert price_root == price_root_arg
        assert horizons == (1, 5, 20)
        events.append("regime_outcomes")
        return RegimeOutcomeResult(
            start_date=start_date,
            end_date=end_date,
            outcomes=(
                RegimeForwardOutcome(
                    source_date=date(2026, 8, 1),
                    price_date=date(2026, 8, 1),
                    regime="risk_on",
                    score=5,
                    confidence="high",
                    horizon_days=1,
                    spy_return=0.01,
                    qqq_return=0.02,
                    spy_max_drawdown=-0.01,
                    qqq_max_drawdown=-0.02,
                ),
            ),
            summary_rows=(
                RegimeOutcomeSummaryRow(
                    bucket="regime:risk_on",
                    horizon_days=1,
                    snapshot_count=1,
                    available_count=1,
                    avg_spy_return=0.01,
                    avg_qqq_return=0.02,
                    avg_spy_max_drawdown=-0.01,
                    avg_qqq_max_drawdown=-0.02,
                ),
            ),
            table="bucket          horizon\nregime:risk_on  1d",
        )

    price_root_arg = price_root
    snapshot_root_arg = snapshot_root
    regime_snapshot_root_arg = regime_snapshot_root
    snapshot_root.mkdir(parents=True)
    (snapshot_root / "2026-08-01.jsonl").write_text("", encoding="utf-8")
    regime_snapshot_root.mkdir(parents=True)
    (regime_snapshot_root / "2026-08-01.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("marketlab.cli.run_daily_workflow", fake_run_daily_workflow)
    monkeypatch.setattr(
        "marketlab.cli.refresh_candidate_price_set",
        fake_refresh_candidate_price_set,
    )
    monkeypatch.setattr("marketlab.cli.refresh_regime_prices", fake_refresh_regime_prices)
    monkeypatch.setattr("marketlab.cli.compute_regime_snapshot", fake_compute_regime_snapshot)
    monkeypatch.setattr(
        "marketlab.cli.validate_bulltard_candidates",
        fake_validate_bulltard_candidates,
    )
    monkeypatch.setattr("marketlab.cli.compute_bulltard_outcomes", fake_compute_bulltard_outcomes)
    monkeypatch.setattr("marketlab.cli.compute_regime_outcomes", fake_compute_regime_outcomes)

    result = CliRunner().invoke(
        app,
        [
            "bulltard",
            "daily",
            str(FIXTURE_DIR / "recap_with_trades_of_interest.html"),
            "--date",
            "2026-08-26",
            "--output-root",
            str(output_root),
            "--debug-root",
            str(debug_root),
            "--fetch-prices",
            "--regime",
            "--regime-snapshot-root",
            str(regime_snapshot_root),
            "--price-start",
            "2025-01-01",
            "--price-end",
            "2026-08-28",
            "--validate",
            "--price-root",
            str(price_root),
            "--snapshot-root",
            str(snapshot_root),
            "--outcomes",
            "--outcome-end",
            "2026-08-26",
            "--horizons",
            "1,5,20",
        ],
    )

    assert result.exit_code == 0
    assert events == [
        "capture",
        "candidate_prices",
        "regime_prices",
        "regime_snapshot",
        "validate",
        "candidate_outcomes",
        "regime_outcomes",
    ]
    assert "price_symbols=META,SPY" in result.output
    assert "price_success_count=2" in result.output
    assert "regime_price_symbols=IWM,RSP,HYG,TLT,^VIX" in result.output
    assert "regime=risk_on" in result.output
    assert "candidate_validation_count=1" in result.output
    assert "candidate_validation_summary=candidates:1 confirm:1 watch:0 avoid:0" in result.output
    assert "META    confirm" in result.output
    assert "outcome_count=1" in result.output
    assert "available_outcome_count=1" in result.output
    assert "regime_outcome_count=1" in result.output
    assert "available_regime_outcome_count=1" in result.output
    assert "all     1d" in result.output
    assert "regime:risk_on  1d" in result.output


def _candidate_snapshot(*, source_date: date, symbol: str) -> CandidateValidationSnapshot:
    return CandidateValidationSnapshot(
        source_date=source_date,
        feature_version="fixture",
        symbol=symbol,
        bulltard_source="ranked+interest#1",
        ranked_side="bullish",
        ranked_score=1.0,
        ranked_trade_count=1,
        ranked_premium=1_000_000.0,
        interest_rank=1,
        detail_rows=1,
        price_date=source_date,
        close=100.0,
        dollar_volume=100_000_000.0,
        return_5d=0.02,
        return_20d=0.1,
        return_60d=0.2,
        ma20_distance=0.03,
        ma50_distance=0.05,
        ma200_distance=None,
        drawdown_60d=-0.04,
        relative_strength_20d_spy=0.05,
        relative_strength_20d_qqq=0.03,
        underlying_liquidity_status="liquid",
        options_liquidity_status="unknown",
        validation_status="confirm",
        validation_reasons=("positive_20d",),
    )


def _candidate_validation_summary(
    *,
    candidate_count: int,
    confirm_count: int = 0,
    watch_count: int = 0,
    avoid_count: int = 0,
    missing_price_count: int = 0,
    thin_underlying_count: int = 0,
) -> CandidateValidationSummary:
    return CandidateValidationSummary(
        candidate_count=candidate_count,
        confirm_count=confirm_count,
        watch_count=watch_count,
        avoid_count=avoid_count,
        missing_price_count=missing_price_count,
        thin_underlying_count=thin_underlying_count,
    )


def _regime_snapshot(*, source_date: date) -> RegimeSnapshot:
    return RegimeSnapshot(
        source_date=source_date,
        feature_version="fixture_features",
        model_version="fixture_model",
        price_date=source_date,
        regime="risk_on",
        score=5,
        confidence="high",
        components=(
            RegimeComponentScore(
                name="trend",
                score=2,
                status="constructive",
                reason="fixture trend",
            ),
        ),
        missing_symbols=(),
        spy_return_20d=0.05,
        spy_return_60d=0.12,
        spy_ma50_distance=0.04,
        spy_ma200_distance=0.10,
        spy_realized_vol_20d=0.12,
        qqq_return_20d=0.06,
        qqq_ma50_distance=0.05,
        qqq_ma200_distance=0.12,
        rsp_spy_relative_20d=0.01,
        iwm_spy_relative_20d=0.02,
        hyg_tlt_relative_20d=0.03,
        vix_close=16.0,
    )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
