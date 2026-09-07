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
from marketlab.charts import OpportunityChartResult, RegimeChartResult
from marketlab.cli import (
    app,
    bulltard_app,
    chart_app,
    gmail_app,
    market_series_app,
    policy_app,
    prices_app,
    regime_app,
    report_app,
    store_app,
)
from marketlab.gmail import GmailAuthResult, GmailBulltardRecapResult
from marketlab.market_series import MarketSeriesFetchResult
from marketlab.market_signals import MarketSignal
from marketlab.policy import DailyPolicyReportResult, PortfolioPolicySnapshot
from marketlab.prices import PriceFetchResult
from marketlab.regime import (
    MarketSignalForwardOutcome,
    MarketSignalOutcomeResult,
    MarketSignalOutcomeSummaryRow,
    RegimeActionForwardOutcome,
    RegimeActionFrequencyRow,
    RegimeActionOutcomeResult,
    RegimeActionOutcomeSummaryRow,
    RegimeActionState,
    RegimeBackfillResult,
    RegimeComponentScore,
    RegimeForwardOutcome,
    RegimeOutcomeResult,
    RegimeOutcomeSummaryRow,
    RegimePressureForwardOutcome,
    RegimePressureOutcomeResult,
    RegimePressureOutcomeSummaryRow,
    RegimePressureSnapshot,
    RegimePriceRefreshResult,
    RegimeSnapshot,
    RegimeSnapshotResult,
)
from marketlab.store import StoreRefreshResult, StoreTableRefresh

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bulltard"


def test_typer_app_has_no_args_is_help_enabled() -> None:
    assert app.info.no_args_is_help is True
    assert bulltard_app.info.no_args_is_help is True
    assert prices_app.info.no_args_is_help is True
    assert market_series_app.info.no_args_is_help is True
    assert gmail_app.info.no_args_is_help is True
    assert regime_app.info.no_args_is_help is True
    assert store_app.info.no_args_is_help is True
    assert policy_app.info.no_args_is_help is True
    assert report_app.info.no_args_is_help is True
    assert chart_app.info.no_args_is_help is True


def test_typer_no_args_shows_help_without_traceback() -> None:
    result = CliRunner().invoke(app, [])

    assert result.exit_code != 0
    assert "MarketLab research workflow CLI." in result.output
    assert "--version" in result.output
    assert "daily" in result.output
    assert "Traceback" not in result.output


def test_daily_run_skips_missing_recap_and_runs_core_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    price_root = tmp_path / "prices"
    market_series_root = tmp_path / "series"
    regime_root = tmp_path / "regime"
    signal_root = tmp_path / "signals"
    candidate_root = tmp_path / "candidates"
    policy_root = tmp_path / "policy"
    db_path = tmp_path / "marketlab.duckdb"

    def fake_refresh_regime_prices(
        *,
        start_date: date,
        end_date: date,
        price_root: Path,
    ) -> RegimePriceRefreshResult:
        assert start_date == date(2025, 2, 27)
        assert end_date == date(2026, 8, 31)
        events.append("regime_prices")
        return RegimePriceRefreshResult(
            start_date=start_date,
            end_date=end_date,
            requested_symbols=("SPY", "QQQ"),
            price_results=(),
            price_failures=(),
        )

    def fake_fetch_and_write_fred_series(
        *,
        series_ids: tuple[str, ...],
        start_date: date,
        end_date: date,
        output_root: Path,
    ) -> tuple[MarketSeriesFetchResult, ...]:
        assert events == ["regime_prices"]
        assert start_date == date(2025, 2, 27)
        assert end_date == date(2026, 8, 31)
        assert output_root == market_series_root
        events.append("market_series")
        return (
            MarketSeriesFetchResult(
                series_id=series_ids[0],
                source_series_id=series_ids[0],
                observation_path=output_root / f"{series_ids[0]}.jsonl",
                row_count=10,
                latest_observed_date=date(2026, 8, 28),
                latest_availability_date=date(2026, 8, 31),
            ),
        )

    def fake_compute_regime_snapshot(
        *,
        source_date: date,
        price_root: Path,
        market_series_root: Path,
        snapshot_root: Path,
        signal_snapshot_root: Path,
        signal_time,
        snapshot_version: str | None,
        write_snapshot: bool,
        overwrite_snapshot: bool,
    ) -> RegimeSnapshotResult:
        assert events == ["regime_prices", "market_series"]
        assert source_date == date(2026, 8, 31)
        assert signal_time == "eod"
        assert snapshot_version is None
        assert write_snapshot is True
        assert overwrite_snapshot is True
        events.append("regime")
        snapshot = _regime_snapshot(source_date=source_date)
        return RegimeSnapshotResult(
            source_date=source_date,
            snapshot=snapshot,
            snapshot_path=snapshot_root / "regime.json",
            table="fixture regime table",
            signals=(),
            signal_snapshot_path=signal_snapshot_root / "market-signals.jsonl",
        )

    def fake_run_daily_workflow(**_kwargs) -> DailyWorkflowResult:
        pytest.fail("Bulltard should be skipped when the default recap file is missing")

    def fake_compute_daily_policy_report(
        *,
        source_date: date,
        regime_snapshot_root: Path,
        market_signal_snapshot_root: Path,
        candidate_snapshot_root: Path,
        policy_snapshot_root: Path,
        signal_time,
        snapshot_version: str | None,
        write_snapshot: bool,
    ) -> DailyPolicyReportResult:
        assert events == ["regime_prices", "market_series", "regime"]
        assert regime_snapshot_root == regime_root
        assert market_signal_snapshot_root == signal_root
        assert candidate_snapshot_root == candidate_root
        assert signal_time == "eod"
        assert snapshot_version is None
        assert write_snapshot is True
        events.append("report")
        policy = _portfolio_policy_snapshot(source_date=source_date)
        return DailyPolicyReportResult(
            source_date=source_date,
            policy=policy,
            previous_policy=None,
            policy_snapshot_path=policy_snapshot_root / "portfolio-policy.json",
            report="fixture daily report",
        )

    def fake_render_regime_chart(
        *,
        start_date: date,
        end_date: date,
        symbol: str,
        comparison_symbol: str | None,
        price_root: Path,
        regime_snapshot_root: Path,
        market_signal_snapshot_root: Path,
        policy_snapshot_root: Path,
        signal_time,
        snapshot_version: str | None,
        output_path: Path | None,
    ) -> RegimeChartResult:
        assert events == ["regime_prices", "market_series", "regime", "report"]
        assert start_date == date(2026, 8, 31)
        assert end_date == date(2026, 8, 31)
        assert symbol == "SPY"
        assert comparison_symbol == "QQQ"
        assert policy_snapshot_root == policy_root
        assert output_path is None
        events.append("chart")
        return RegimeChartResult(
            start_date=start_date,
            end_date=end_date,
            output_path=tmp_path / "reports" / "regime.html",
            price_symbols=("SPY", "QQQ"),
            price_point_count=10,
            regime_snapshot_count=1,
            market_signal_count=4,
            policy_snapshot_count=1,
        )

    def fake_refresh_research_store(
        *,
        db_path: Path,
        price_root: Path,
        market_series_root: Path,
        regime_snapshot_root: Path,
        market_signal_snapshot_root: Path,
        candidate_snapshot_root: Path,
        policy_snapshot_root: Path,
        bulltard_observation_root: Path,
    ) -> StoreRefreshResult:
        assert events == ["regime_prices", "market_series", "regime", "report", "chart"]
        assert db_path == db_path_arg
        assert bulltard_observation_root == bulltard_root_arg
        events.append("store")
        return StoreRefreshResult(
            db_path=db_path,
            schema_version="fixture_store",
            table_refreshes=(StoreTableRefresh(table_name="regime_snapshots", row_count=1),),
        )

    bulltard_root_arg = tmp_path / "bulltard"
    db_path_arg = db_path
    monkeypatch.setattr("marketlab.cli.refresh_regime_prices", fake_refresh_regime_prices)
    monkeypatch.setattr(
        "marketlab.cli.fetch_and_write_fred_series",
        fake_fetch_and_write_fred_series,
    )
    monkeypatch.setattr("marketlab.cli.compute_regime_snapshot", fake_compute_regime_snapshot)
    monkeypatch.setattr("marketlab.cli.run_daily_workflow", fake_run_daily_workflow)
    monkeypatch.setattr(
        "marketlab.cli.compute_daily_policy_report",
        fake_compute_daily_policy_report,
    )
    monkeypatch.setattr("marketlab.cli.render_regime_chart", fake_render_regime_chart)
    monkeypatch.setattr("marketlab.cli.refresh_research_store", fake_refresh_research_store)

    result = CliRunner().invoke(
        app,
        [
            "daily",
            "--date",
            "2026-08-31",
            "--no-gmail",
            "--price-root",
            str(price_root),
            "--market-series-root",
            str(market_series_root),
            "--bulltard-root",
            str(bulltard_root_arg),
            "--regime-root",
            str(regime_root),
            "--signal-root",
            str(signal_root),
            "--candidate-root",
            str(candidate_root),
            "--policy-root",
            str(policy_root),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert events == ["regime_prices", "market_series", "regime", "report", "chart", "store"]
    assert "daily_date=2026-08-31" in result.output
    assert "bulltard_status=skipped_missing_recap" in result.output
    assert "fixture daily report" in result.output
    assert "daily_status=complete" in result.output
    assert "bulltard_ran=false" in result.output


def test_daily_run_uses_default_recap_file_for_bulltard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    recap_path = tmp_path / "data" / "inbox" / "bulltard" / "recap-2026-08-31.html"
    recap_path.parent.mkdir(parents=True)
    recap_path.write_text("fixture recap", encoding="utf-8")
    events: list[str] = []

    def fake_refresh_regime_prices(
        *,
        start_date: date,
        end_date: date,
        price_root: Path,
    ) -> RegimePriceRefreshResult:
        assert start_date == date(2025, 2, 27)
        assert end_date == date(2026, 8, 31)
        events.append("regime_prices")
        return RegimePriceRefreshResult(
            start_date=start_date,
            end_date=end_date,
            requested_symbols=("SPY", "QQQ"),
            price_results=(),
            price_failures=(),
        )

    def fake_compute_regime_snapshot(
        *,
        source_date: date,
        price_root: Path,
        market_series_root: Path,
        snapshot_root: Path,
        signal_snapshot_root: Path,
        signal_time,
        snapshot_version: str | None,
        write_snapshot: bool,
        overwrite_snapshot: bool,
    ) -> RegimeSnapshotResult:
        assert events == ["regime_prices"]
        assert overwrite_snapshot is True
        events.append("regime")
        return RegimeSnapshotResult(
            source_date=source_date,
            snapshot=_regime_snapshot(source_date=source_date),
            snapshot_path=snapshot_root / "regime.json",
            table="fixture regime table",
            signals=(),
            signal_snapshot_path=signal_snapshot_root / "market-signals.jsonl",
        )

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
        assert events == ["regime_prices", "regime"]
        assert source_date == date(2026, 8, 31)
        assert recap_path == Path("data/inbox/bulltard/recap-2026-08-31.html")
        assert fetch_ticker_details is True
        assert top_ranked == 2
        assert extra_tickers == ("META",)
        assert limit == 3
        events.append("bulltard")
        plan = IngestPlan(
            source_date=source_date,
            view=BulltardView.RANKED_OPTION_TRADES,
            recap_path=recap_path,
            signed_url="https://jamesbulltard.substack.com/redirect?token=fixture-secret",
            observation_path=output_root / "ranked_option_trades" / "2026-08-31.jsonl",
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
                    debug_path=debug_root / "ranked_option_trades" / "2026-08-31.html",
                ),
                row_count=40,
                observation_path=plan.observation_path,
            ),
            trades_of_interest_result=TradesOfInterestIngestResult(
                source_date=source_date,
                recap_path=recap_path,
                row_count=1,
                observation_path=output_root / "trades_of_interest" / "2026-08-31.jsonl",
                symbols=("META",),
            ),
            ticker_results=(),
            ticker_failures=(),
            candidate_table="symbol source\nMETA   ranked+interest#1",
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
        assert events == ["regime_prices", "regime", "bulltard"]
        events.append("candidate_prices")
        return CandidatePriceRefreshResult(
            source_date=source_date,
            start_date=start_date,
            end_date=end_date,
            requested_symbols=("META", "SPY", "QQQ"),
            price_results=(),
            price_failures=(),
        )

    def fake_validate_bulltard_candidates(
        *,
        source_date: date,
        observations_root: Path,
        price_root: Path,
        snapshot_root: Path,
        limit: int,
        min_dollar_volume: float,
        signal_time,
        snapshot_version: str | None,
        write_snapshot: bool,
    ) -> CandidateValidationResult:
        assert events == ["regime_prices", "regime", "bulltard", "candidate_prices"]
        assert limit == 3
        assert signal_time == "eod"
        assert snapshot_version is None
        events.append("validate")
        return CandidateValidationResult(
            source_date=source_date,
            snapshots=(),
            snapshot_path=snapshot_root / "candidate-validation.jsonl",
            summary=CandidateValidationSummary(
                candidate_count=0,
                confirm_count=0,
                watch_count=0,
                avoid_count=0,
                missing_price_count=0,
                thin_underlying_count=0,
            ),
            table="fixture validation table",
        )

    def fake_compute_bulltard_outcomes(
        *,
        start_date: date,
        end_date: date,
        snapshot_root: Path,
        price_root: Path,
        observations_root: Path,
        regime_snapshot_root: Path | None,
        horizons: tuple[int, ...],
    ) -> CandidateOutcomeResult:
        assert events == ["regime_prices", "regime", "bulltard", "candidate_prices", "validate"]
        assert start_date == date(2026, 8, 31)
        assert end_date == date(2026, 8, 31)
        assert observations_root == Path("data/observations/bulltard")
        assert regime_snapshot_root == Path("data/snapshots/regime/market")
        assert horizons == (1, 5, 20, 40, 65, 126)
        events.append("outcomes")
        return CandidateOutcomeResult(
            start_date=start_date,
            end_date=end_date,
            outcomes=(),
            summary_rows=(),
            table="No outcome rows found.",
        )

    def fake_compute_daily_policy_report(**kwargs) -> DailyPolicyReportResult:
        assert events == [
            "regime_prices",
            "regime",
            "bulltard",
            "candidate_prices",
            "validate",
            "outcomes",
        ]
        source_date = kwargs["source_date"]
        events.append("report")
        policy = _portfolio_policy_snapshot(source_date=source_date)
        return DailyPolicyReportResult(
            source_date=source_date,
            policy=policy,
            previous_policy=None,
            policy_snapshot_path=Path("policy.json"),
            report="fixture daily report",
        )

    monkeypatch.setattr("marketlab.cli.refresh_regime_prices", fake_refresh_regime_prices)
    monkeypatch.setattr("marketlab.cli.compute_regime_snapshot", fake_compute_regime_snapshot)
    monkeypatch.setattr("marketlab.cli.run_daily_workflow", fake_run_daily_workflow)
    monkeypatch.setattr(
        "marketlab.cli.refresh_candidate_price_set",
        fake_refresh_candidate_price_set,
    )
    monkeypatch.setattr(
        "marketlab.cli.validate_bulltard_candidates",
        fake_validate_bulltard_candidates,
    )
    monkeypatch.setattr("marketlab.cli.compute_bulltard_outcomes", fake_compute_bulltard_outcomes)
    monkeypatch.setattr(
        "marketlab.cli.compute_daily_policy_report",
        fake_compute_daily_policy_report,
    )

    result = CliRunner().invoke(
        app,
        [
            "daily",
            "--date",
            "2026-08-31",
            "--no-market-series",
            "--no-chart",
            "--no-store",
            "--top-ranked",
            "2",
            "--ticker",
            "META",
            "--limit",
            "3",
        ],
    )

    assert result.exit_code == 0
    assert events == [
        "regime_prices",
        "regime",
        "bulltard",
        "candidate_prices",
        "validate",
        "outcomes",
        "report",
    ]
    assert "ranked_row_count=40" in result.output
    assert "candidate_validation_count=0" in result.output
    assert "fixture daily report" in result.output
    assert "bulltard_ran=true" in result.output


def test_daily_run_fetches_missing_default_recap_from_gmail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    client_secret_path = tmp_path / "secrets" / "google-oauth-client.json"
    token_path = tmp_path / "secrets" / "gmail-token.json"
    client_secret_path.parent.mkdir(parents=True)
    client_secret_path.write_text("{}", encoding="utf-8")
    token_path.write_text("{}", encoding="utf-8")
    events: list[str] = []

    def fake_compute_regime_snapshot(
        *,
        source_date: date,
        price_root: Path,
        market_series_root: Path,
        snapshot_root: Path,
        signal_snapshot_root: Path,
        signal_time,
        snapshot_version: str | None,
        write_snapshot: bool,
        overwrite_snapshot: bool,
    ) -> RegimeSnapshotResult:
        assert source_date == date(2026, 9, 1)
        assert overwrite_snapshot is True
        events.append("regime")
        return RegimeSnapshotResult(
            source_date=source_date,
            snapshot=_regime_snapshot(source_date=source_date),
            snapshot_path=snapshot_root / "regime.json",
            table="fixture regime table",
            signals=(),
            signal_snapshot_path=signal_snapshot_root / "market-signals.jsonl",
        )

    def fake_fetch_bulltard_recap_from_gmail(
        *,
        source_date: date,
        client_secret_path: Path,
        token_path: Path,
        output_root: Path,
        query: str | None,
    ) -> GmailBulltardRecapResult:
        assert events == ["regime"]
        assert source_date == date(2026, 9, 1)
        assert client_secret_path == Path("secrets/google-oauth-client.json")
        assert token_path == Path("secrets/gmail-token.json")
        assert output_root == Path("data/inbox/bulltard")
        assert query == "fixture gmail query"
        recap_path = output_root / "recap-2026-09-01.html"
        recap_path.parent.mkdir(parents=True)
        recap_path.write_text("fixture recap", encoding="utf-8")
        events.append("gmail")
        return GmailBulltardRecapResult(
            source_date=source_date,
            message_id="message-1",
            thread_id="thread-1",
            subject="Bulltard recap",
            sender="James <james@example.com>",
            received_at="Tue, 1 Sep 2026 13:00:00 -0700",
            recap_path=recap_path,
            signed_url="https://substack.com/redirect/fixture?j=token",
            query=query or "",
        )

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
        assert events == ["regime", "gmail"]
        assert recap_path == Path("data/inbox/bulltard/recap-2026-09-01.html")
        events.append("bulltard")
        plan = IngestPlan(
            source_date=source_date,
            view=BulltardView.RANKED_OPTION_TRADES,
            recap_path=recap_path,
            signed_url="https://substack.com/redirect/fixture?j=token",
            observation_path=output_root / "ranked_option_trades" / "2026-09-01.jsonl",
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
                    debug_path=debug_root / "ranked_option_trades" / "2026-09-01.html",
                ),
                row_count=40,
                observation_path=plan.observation_path,
            ),
            trades_of_interest_result=None,
            ticker_results=(),
            ticker_failures=(),
            candidate_table="symbol source\nMETA   ranked",
        )

    def fake_validate_bulltard_candidates(**kwargs) -> CandidateValidationResult:
        assert events == ["regime", "gmail", "bulltard"]
        events.append("validate")
        source_date = kwargs["source_date"]
        return CandidateValidationResult(
            source_date=source_date,
            snapshots=(),
            snapshot_path=Path("candidate-validation.jsonl"),
            summary=CandidateValidationSummary(
                candidate_count=0,
                confirm_count=0,
                watch_count=0,
                avoid_count=0,
                missing_price_count=0,
                thin_underlying_count=0,
            ),
            table="fixture validation table",
        )

    def fake_compute_daily_policy_report(**kwargs) -> DailyPolicyReportResult:
        assert events == ["regime", "gmail", "bulltard", "validate"]
        events.append("report")
        source_date = kwargs["source_date"]
        policy = _portfolio_policy_snapshot(source_date=source_date)
        return DailyPolicyReportResult(
            source_date=source_date,
            policy=policy,
            previous_policy=None,
            policy_snapshot_path=Path("policy.json"),
            report="fixture daily report",
        )

    monkeypatch.setattr("marketlab.cli.compute_regime_snapshot", fake_compute_regime_snapshot)
    monkeypatch.setattr(
        "marketlab.cli.fetch_bulltard_recap_from_gmail",
        fake_fetch_bulltard_recap_from_gmail,
    )
    monkeypatch.setattr("marketlab.cli.run_daily_workflow", fake_run_daily_workflow)
    monkeypatch.setattr(
        "marketlab.cli.validate_bulltard_candidates", fake_validate_bulltard_candidates
    )
    monkeypatch.setattr(
        "marketlab.cli.compute_daily_policy_report", fake_compute_daily_policy_report
    )

    result = CliRunner().invoke(
        app,
        [
            "daily",
            "--date",
            "2026-09-01",
            "--no-prices",
            "--no-market-series",
            "--no-chart",
            "--no-store",
            "--no-outcomes",
            "--gmail-query",
            "fixture gmail query",
        ],
    )

    assert result.exit_code == 0
    assert events == ["regime", "gmail", "bulltard", "validate", "report"]
    assert "gmail_recap_path=data/inbox/bulltard/recap-2026-09-01.html" in result.output
    assert "gmail_message_id=message-1" in result.output
    assert "bulltard_ran=true" in result.output


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


def test_market_series_no_args_shows_help_without_traceback() -> None:
    result = CliRunner().invoke(app, ["market-series"])

    assert result.exit_code != 0
    assert "Scalar market series utilities." in result.output
    assert "fetch-fred" in result.output
    assert "Traceback" not in result.output


def test_gmail_no_args_shows_help_without_traceback() -> None:
    result = CliRunner().invoke(app, ["gmail"])

    assert result.exit_code != 0
    assert "Find Bulltard recap emails in Gmail" in result.output
    assert "auth" in result.output
    assert "bulltard-recap" in result.output
    assert "Traceback" not in result.output


def test_gmail_auth_no_args_shows_help_without_default_path_error() -> None:
    result = CliRunner().invoke(app, ["gmail", "auth"])

    assert result.exit_code != 0
    assert "Authorize read-only Gmail access" in result.output
    assert "--client-secret" in result.output
    assert "not your Gmail" in result.output
    assert "password" in result.output
    assert "Local 127.0.0.1" in result.output
    assert "callback" in result.output
    assert "port" in result.output
    assert "--no-browser" in result.output
    assert "SSH/headless" in result.output
    assert "Invalid value" not in result.output
    assert "Traceback" not in result.output


def test_gmail_bulltard_recap_no_args_shows_help_without_missing_date_error() -> None:
    result = CliRunner().invoke(app, ["gmail", "bulltard-recap"])

    assert result.exit_code != 0
    assert "cache it for Bulltard ingest" in result.output
    assert "--date" in result.output
    assert "Existing local Gmail token" in result.output
    assert "marketlab gmail" in result.output
    assert "auth" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_gmail_auth_outputs_token_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_secret_path = tmp_path / "client-secret.json"
    token_path = tmp_path / "gmail-token.json"
    client_secret_path.write_text("{}", encoding="utf-8")

    def fake_run_gmail_oauth_flow(
        *,
        client_secret_path: Path,
        token_path: Path,
        port: int,
        open_browser: bool,
        timeout_seconds: int,
        auth_url_callback,
    ) -> GmailAuthResult:
        assert client_secret_path == client_secret_path_arg
        assert token_path == token_path_arg
        assert port == 8765
        assert open_browser is False
        assert timeout_seconds == 12
        auth_url_callback("https://accounts.google.com/o/oauth2/v2/auth?fixture=1")
        return GmailAuthResult(
            token_path=token_path,
            scope="https://www.googleapis.com/auth/gmail.readonly",
            expires_at="2026-09-01T20:00:00+00:00",
        )

    client_secret_path_arg = client_secret_path
    token_path_arg = token_path
    monkeypatch.setattr("marketlab.cli.run_gmail_oauth_flow", fake_run_gmail_oauth_flow)

    result = CliRunner().invoke(
        app,
        [
            "gmail",
            "auth",
            "--client-secret",
            str(client_secret_path),
            "--token",
            str(token_path),
            "--port",
            "8765",
            "--no-browser",
            "--timeout-seconds",
            "12",
        ],
    )

    assert result.exit_code == 0
    assert (
        "authorization_url=https://accounts.google.com/o/oauth2/v2/auth?fixture=1" in result.output
    )
    assert f"gmail_token_path={token_path}" in result.output
    assert "gmail_scope=https://www.googleapis.com/auth/gmail.readonly" in result.output


def test_gmail_bulltard_recap_outputs_cached_recap_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_secret_path = tmp_path / "client-secret.json"
    token_path = tmp_path / "gmail-token.json"
    output_root = tmp_path / "inbox"
    client_secret_path.write_text("{}", encoding="utf-8")
    token_path.write_text("{}", encoding="utf-8")

    def fake_fetch_bulltard_recap_from_gmail(
        *,
        source_date: date,
        client_secret_path: Path,
        token_path: Path,
        output_root: Path,
        query: str | None,
        max_results: int,
        overwrite: bool,
    ) -> GmailBulltardRecapResult:
        assert source_date == date(2026, 9, 1)
        assert client_secret_path == client_secret_path_arg
        assert token_path == token_path_arg
        assert output_root == output_root_arg
        assert query == "fixture query"
        assert max_results == 5
        assert overwrite is True
        return GmailBulltardRecapResult(
            source_date=source_date,
            message_id="message-1",
            thread_id="thread-1",
            subject="Bulltard recap",
            sender="James <james@example.com>",
            received_at="Tue, 1 Sep 2026 13:00:00 -0700",
            recap_path=output_root / "recap-2026-09-01.html",
            signed_url="https://substack.com/redirect/fixture?j=token",
            query=query or "",
        )

    client_secret_path_arg = client_secret_path
    token_path_arg = token_path
    output_root_arg = output_root
    monkeypatch.setattr(
        "marketlab.cli.fetch_bulltard_recap_from_gmail",
        fake_fetch_bulltard_recap_from_gmail,
    )

    result = CliRunner().invoke(
        app,
        [
            "gmail",
            "bulltard-recap",
            "--date",
            "2026-09-01",
            "--client-secret",
            str(client_secret_path),
            "--token",
            str(token_path),
            "--output-root",
            str(output_root),
            "--query",
            "fixture query",
            "--max-results",
            "5",
            "--overwrite",
        ],
    )

    assert result.exit_code == 0
    assert f"gmail_recap_path={output_root / 'recap-2026-09-01.html'}" in result.output
    assert "gmail_message_id=message-1" in result.output
    assert "gmail_subject=Bulltard recap" in result.output
    assert "gmail_query=fixture query" in result.output


def test_regime_no_args_shows_help_without_traceback() -> None:
    result = CliRunner().invoke(app, ["regime"])

    assert result.exit_code != 0
    assert "Market regime utilities." in result.output
    assert "snapshot" in result.output
    assert "Traceback" not in result.output


def test_store_no_args_shows_help_without_traceback() -> None:
    result = CliRunner().invoke(app, ["store"])

    assert result.exit_code != 0
    assert "Local research store utilities." in result.output
    assert "refresh" in result.output
    assert "Traceback" not in result.output


def test_policy_no_args_shows_help_without_traceback() -> None:
    result = CliRunner().invoke(app, ["policy"])

    assert result.exit_code != 0
    assert "Portfolio policy utilities." in result.output
    assert "snapshot" in result.output
    assert "outcomes" in result.output
    assert "Traceback" not in result.output


def test_report_no_args_shows_help_without_traceback() -> None:
    result = CliRunner().invoke(app, ["report"])

    assert result.exit_code != 0
    assert "Human-readable research reports." in result.output
    assert "daily" in result.output
    assert "Traceback" not in result.output


def test_chart_no_args_shows_help_without_traceback() -> None:
    result = CliRunner().invoke(app, ["chart"])

    assert result.exit_code != 0
    assert "Reproducible chart utilities." in result.output
    assert "regime" in result.output
    assert "opportunity" in result.output
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


def test_market_series_fetch_fred_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["market-series", "fetch-fred"])

    assert result.exit_code != 0
    assert "Fetch scalar market series observations from FRED" in result.output
    assert "SERIES[,SERIES...]" in result.output
    assert "--start" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_regime_snapshot_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["regime", "snapshot"])

    assert result.exit_code != 0
    assert "Compute a market regime snapshot" in result.output
    assert "--date" in result.output
    assert "--fetch-prices" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_regime_backfill_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["regime", "backfill"])

    assert result.exit_code != 0
    assert "Backfill daily market regime snapshots and market signal artifacts" in result.output
    assert "--start" in result.output
    assert "--end" in result.output
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


def test_regime_signal_outcomes_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["regime", "signal-outcomes"])

    assert result.exit_code != 0
    assert "Replay forward SPY/QQQ outcomes" in result.output
    assert "--start" in result.output
    assert "--end" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_regime_action_outcomes_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["regime", "action-outcomes"])

    assert result.exit_code != 0
    assert "Replay forward SPY/QQQ outcomes for rare regime action states" in result.output
    assert "--start" in result.output
    assert "--end" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_regime_pressure_outcomes_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["regime", "pressure-outcomes"])

    assert result.exit_code != 0
    assert "Replay forward SPY/QQQ outcomes for normalized pressure buckets" in result.output
    assert "--start" in result.output
    assert "--end" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_store_refresh_no_args_runs_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_refresh_research_store(**kwargs):  # noqa: ANN003
        assert kwargs["db_path"].name == "marketlab.duckdb"
        return StoreRefreshResult(
            db_path=kwargs["db_path"],
            schema_version="fixture",
            table_refreshes=(StoreTableRefresh(table_name="regime_snapshots", row_count=1),),
        )

    monkeypatch.setattr("marketlab.cli.refresh_research_store", fake_refresh_research_store)

    result = CliRunner().invoke(app, ["store", "refresh"])

    assert result.exit_code == 0
    assert "research_db_path=marketlab.duckdb" in result.output
    assert "regime_snapshots" in result.output
    assert "Traceback" not in result.output


def test_store_query_no_args_shows_help_without_missing_argument_error() -> None:
    result = CliRunner().invoke(app, ["store", "query"])

    assert result.exit_code != 0
    assert "Run a read-only SQL query" in result.output
    assert "SQL" in result.output
    assert "Missing argument" not in result.output
    assert "Traceback" not in result.output


def test_policy_snapshot_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["policy", "snapshot"])

    assert result.exit_code != 0
    assert "Compute a portfolio policy snapshot" in result.output
    assert "--date" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_policy_backfill_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["policy", "backfill"])

    assert result.exit_code != 0
    assert "Backfill portfolio policy snapshots" in result.output
    assert "--start" in result.output
    assert "--end" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_policy_outcomes_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["policy", "outcomes"])

    assert result.exit_code != 0
    assert "Replay portfolio policy snapshots" in result.output
    assert "--start" in result.output
    assert "--end" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_report_daily_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["report", "daily"])

    assert result.exit_code != 0
    assert "Render the daily market regime and portfolio policy report" in result.output
    assert "--date" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_chart_regime_no_args_shows_help_without_missing_option_error() -> None:
    result = CliRunner().invoke(app, ["chart", "regime"])

    assert result.exit_code != 0
    assert "Render a reproducible market regime chart" in result.output
    assert "--start" in result.output
    assert "--end" in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_chart_opportunity_no_args_shows_help_without_missing_argument_error() -> None:
    result = CliRunner().invoke(app, ["chart", "opportunity"])

    assert result.exit_code != 0
    assert "Render a reproducible single-name opportunity chart" in result.output
    assert "SYMBOL" in result.output
    assert "--date" in result.output
    assert "Missing argument" not in result.output
    assert "Missing option" not in result.output
    assert "Traceback" not in result.output


def test_chart_regime_outputs_chart_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    price_root = tmp_path / "prices"
    regime_root = tmp_path / "regime"
    signal_root = tmp_path / "signals"
    policy_root = tmp_path / "policy"
    output_path = tmp_path / "reports" / "regime.html"

    def fake_render_regime_chart(
        *,
        start_date: date,
        end_date: date,
        symbol: str,
        comparison_symbol: str | None,
        price_root: Path,
        regime_snapshot_root: Path,
        market_signal_snapshot_root: Path,
        policy_snapshot_root: Path,
        signal_time,
        snapshot_version: str | None,
        output_path: Path | None,
    ) -> RegimeChartResult:
        assert start_date == date(2026, 1, 1)
        assert end_date == date(2026, 8, 28)
        assert symbol == "SPY"
        assert comparison_symbol == "QQQ"
        assert price_root == price_root_arg
        assert regime_snapshot_root == regime_root_arg
        assert market_signal_snapshot_root == signal_root_arg
        assert policy_snapshot_root == policy_root_arg
        assert signal_time == "eod"
        assert snapshot_version is None
        assert output_path == output_path_arg
        return RegimeChartResult(
            start_date=start_date,
            end_date=end_date,
            output_path=output_path_arg,
            price_symbols=("SPY", "QQQ"),
            price_point_count=420,
            regime_snapshot_count=20,
            market_signal_count=160,
            policy_snapshot_count=18,
        )

    price_root_arg = price_root
    regime_root_arg = regime_root
    signal_root_arg = signal_root
    policy_root_arg = policy_root
    output_path_arg = output_path
    monkeypatch.setattr("marketlab.cli.render_regime_chart", fake_render_regime_chart)

    result = CliRunner().invoke(
        app,
        [
            "chart",
            "regime",
            "--start",
            "2026-01-01",
            "--end",
            "2026-08-28",
            "--price-root",
            str(price_root),
            "--regime-root",
            str(regime_root),
            "--signal-root",
            str(signal_root),
            "--policy-root",
            str(policy_root),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert f"chart_path={output_path}" in result.output
    assert "chart_version=regime_chart_v0" in result.output
    assert "chart_price_symbols=SPY,QQQ" in result.output
    assert "chart_price_point_count=420" in result.output
    assert "regime_snapshot_count=20" in result.output
    assert "market_signal_count=160" in result.output
    assert "policy_snapshot_count=18" in result.output


def test_chart_opportunity_outputs_chart_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    price_root = tmp_path / "prices"
    candidate_root = tmp_path / "candidates"
    observations_root = tmp_path / "observations" / "bulltard"
    output_path = tmp_path / "reports" / "opportunity.html"

    def fake_render_opportunity_chart(
        *,
        source_date: date,
        symbol: str,
        lookback_days: int,
        forward_days: int,
        price_root: Path,
        candidate_snapshot_root: Path,
        observations_root: Path,
        signal_time,
        snapshot_version: str | None,
        output_path: Path | None,
    ) -> OpportunityChartResult:
        assert source_date == date(2026, 8, 28)
        assert symbol == "MRVL"
        assert lookback_days == 90
        assert forward_days == 30
        assert price_root == price_root_arg
        assert candidate_snapshot_root == candidate_root_arg
        assert observations_root == observations_root_arg
        assert signal_time == "eod"
        assert snapshot_version is None
        assert output_path == output_path_arg
        return OpportunityChartResult(
            source_date=source_date,
            symbol="MRVL",
            output_path=output_path_arg,
            chart_start_date=date(2026, 5, 30),
            chart_end_date=date(2026, 9, 27),
            price_symbols=("MRVL", "SPY", "QQQ"),
            price_point_count=240,
            flow_event_count=12,
            available_forward_outcome_count=3,
            validation_status="watch",
        )

    price_root_arg = price_root
    candidate_root_arg = candidate_root
    observations_root_arg = observations_root
    output_path_arg = output_path
    monkeypatch.setattr(
        "marketlab.cli.render_opportunity_chart",
        fake_render_opportunity_chart,
    )

    result = CliRunner().invoke(
        app,
        [
            "chart",
            "opportunity",
            "MRVL",
            "--date",
            "2026-08-28",
            "--lookback-days",
            "90",
            "--forward-days",
            "30",
            "--price-root",
            str(price_root),
            "--candidate-root",
            str(candidate_root),
            "--observations-root",
            str(observations_root),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert f"chart_path={output_path}" in result.output
    assert "chart_version=opportunity_chart_v0" in result.output
    assert "chart_symbol=MRVL" in result.output
    assert "chart_source_date=2026-08-28" in result.output
    assert "chart_price_symbols=MRVL,SPY,QQQ" in result.output
    assert "chart_price_point_count=240" in result.output
    assert "flow_event_count=12" in result.output
    assert "available_forward_outcome_count=3" in result.output
    assert "validation_status=watch" in result.output


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


def test_market_series_fetch_fred_outputs_written_observation_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "series"

    def fake_fetch_and_write_fred_series(
        *,
        series_ids: tuple[str, ...],
        start_date: date,
        end_date: date,
        output_root: Path,
    ) -> tuple[MarketSeriesFetchResult, ...]:
        assert series_ids == ("BAMLH0A0HYM2", "NFCI")
        assert start_date == date(2026, 1, 1)
        assert end_date == date(2026, 8, 28)
        return (
            MarketSeriesFetchResult(
                series_id="BAMLH0A0HYM2",
                source_series_id="BAMLH0A0HYM2",
                observation_path=output_root / "BAMLH0A0HYM2.jsonl",
                row_count=100,
                latest_observed_date=date(2026, 8, 27),
                latest_availability_date=date(2026, 8, 28),
            ),
        )

    monkeypatch.setattr(
        "marketlab.cli.fetch_and_write_fred_series",
        fake_fetch_and_write_fred_series,
    )

    result = CliRunner().invoke(
        app,
        [
            "market-series",
            "fetch-fred",
            "BAMLH0A0HYM2,NFCI",
            "--start",
            "2026-01-01",
            "--end",
            "2026-08-28",
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0
    assert "market_series_ids=BAMLH0A0HYM2" in result.output
    assert "market_series_success_count=1" in result.output
    assert "market_series_result=BAMLH0A0HYM2 row_count=100" in result.output
    assert str(output_root / "BAMLH0A0HYM2.jsonl") in result.output


def test_regime_snapshot_fetches_prices_and_outputs_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    price_root = tmp_path / "prices"
    market_series_root = tmp_path / "market-series"
    snapshot_root = tmp_path / "regime"
    signal_snapshot_root = tmp_path / "signals"
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

    def fake_fetch_and_write_fred_series(
        *,
        series_ids: tuple[str, ...],
        start_date: date,
        end_date: date,
        output_root: Path,
    ) -> tuple[MarketSeriesFetchResult, ...]:
        assert events == ["prices"]
        assert series_ids == ("BAMLH0A0HYM2", "NFCI", "DGS10", "DGS2")
        assert start_date == date(2025, 1, 1)
        assert end_date == date(2026, 8, 28)
        assert output_root == market_series_root_arg
        events.append("market-series")
        return (
            MarketSeriesFetchResult(
                series_id="BAMLH0A0HYM2",
                source_series_id="BAMLH0A0HYM2",
                observation_path=output_root / "BAMLH0A0HYM2.jsonl",
                row_count=420,
                latest_observed_date=date(2026, 8, 27),
                latest_availability_date=date(2026, 8, 28),
            ),
        )

    def fake_compute_regime_snapshot(
        *,
        source_date: date,
        price_root: Path,
        market_series_root: Path,
        snapshot_root: Path,
        signal_snapshot_root: Path,
        signal_time,
        snapshot_version: str | None,
        write_snapshot: bool,
        overwrite_snapshot: bool,
    ) -> RegimeSnapshotResult:
        assert events == ["prices", "market-series"]
        assert source_date == date(2026, 8, 28)
        assert price_root == price_root_arg
        assert market_series_root == market_series_root_arg
        assert snapshot_root == snapshot_root_arg
        assert signal_snapshot_root == signal_snapshot_root_arg
        assert signal_time == "eod"
        assert snapshot_version is None
        assert write_snapshot is True
        assert overwrite_snapshot is True
        events.append("snapshot")
        snapshot = _regime_snapshot(source_date=source_date)
        signal = MarketSignal(
            source_date=source_date,
            feature_version="fixture",
            family="trend",
            name="price_proxy",
            status="constructive",
            score=2,
            value="SPY fixture",
            unit="text",
            source="fixture",
            observed_date=source_date,
            availability_date=source_date,
            reason="fixture signal",
        )
        return RegimeSnapshotResult(
            source_date=source_date,
            snapshot=snapshot,
            snapshot_path=snapshot_root / "2026-08-28.json",
            table="component  score  status\ntrend     +2     constructive",
            signals=(signal,),
            signal_snapshot_path=signal_snapshot_root / "2026-08-28.jsonl",
            signal_table="family  signal       score\ntrend   price_proxy  +2",
            contradictions=("positive=trend/price_proxy:constructive negative=fixture",),
            action=RegimeActionState(
                source_date=source_date,
                action_version="fixture_action",
                state="no_change",
                stretch_score=1,
                washout_score=0,
                confidence="high",
                reason="No rare-action threshold crossed; maintain current posture",
                evidence=("strong SPY rally",),
            ),
            pressure=RegimePressureSnapshot(
                source_date=source_date,
                pressure_version="fixture_pressure",
                stretch_pressure_score=0.42,
                washout_pressure_score=0.08,
                confidence="medium",
                features=(),
            ),
            pressure_table="family  feature         stretch\ntrend   spy_return_20d  0.42",
        )

    price_root_arg = price_root
    market_series_root_arg = market_series_root
    snapshot_root_arg = snapshot_root
    signal_snapshot_root_arg = signal_snapshot_root
    monkeypatch.setattr("marketlab.cli.refresh_regime_prices", fake_refresh_regime_prices)
    monkeypatch.setattr(
        "marketlab.cli.fetch_and_write_fred_series",
        fake_fetch_and_write_fred_series,
    )
    monkeypatch.setattr("marketlab.cli.compute_regime_snapshot", fake_compute_regime_snapshot)

    result = CliRunner().invoke(
        app,
        [
            "regime",
            "snapshot",
            "--date",
            "2026-08-28",
            "--refresh-sources",
            "--overwrite",
            "--price-start",
            "2025-01-01",
            "--price-end",
            "2026-08-28",
            "--market-series-start",
            "2025-01-01",
            "--market-series-end",
            "2026-08-28",
            "--price-root",
            str(price_root),
            "--market-series-root",
            str(market_series_root),
            "--snapshot-root",
            str(snapshot_root),
            "--signal-root",
            str(signal_snapshot_root),
        ],
    )

    assert result.exit_code == 0
    assert events == ["prices", "market-series", "snapshot"]
    assert "regime_price_symbols=SPY,QQQ" in result.output
    assert "regime_price_success_count=1" in result.output
    assert "market_series_ids=BAMLH0A0HYM2" in result.output
    assert "market_series_success_count=1" in result.output
    assert f"regime_snapshot_path={snapshot_root / '2026-08-28.json'}" in result.output
    assert (
        f"market_signal_artifact_path={signal_snapshot_root / '2026-08-28.jsonl'}"
        in result.output
    )
    assert "market_signal_count=1" in result.output
    assert "trend   price_proxy  +2" in result.output
    assert "regime_date=2026-08-28" in result.output
    assert "signal" in result.output
    assert "value" in result.output
    assert "risk_on (+5)" in result.output
    assert "action" in result.output
    assert "no_change" in result.output
    assert "pressure_feature_count=0" in result.output
    assert "stretch 0.42 / washout 0.08" in result.output
    assert "medium confidence" in result.output
    assert "positive=trend/price_proxy:constructive negative=fixture" in result.output
    assert "trend   spy_return_20d  0.42" in result.output
    assert "regime=risk_on" not in result.output
    assert "regime_score=5" not in result.output
    assert "action_state=no_change" not in result.output
    assert "no_change (stretch 1 / washout 0)" not in result.output
    assert "stretch_score=1" not in result.output
    assert "washout_score=0" not in result.output
    assert "action_confidence=high" not in result.output
    assert "stretch_pressure_score=0.42" not in result.output
    assert "washout_pressure_score=0.08" not in result.output
    assert "pressure_confidence=medium" not in result.output
    assert "market_signal_contradictions=" not in result.output
    assert "component  score  status" not in result.output
    assert "trend     +2     constructive" not in result.output


def test_regime_backfill_fetches_sources_once_and_outputs_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    price_root = tmp_path / "prices"
    market_series_root = tmp_path / "market-series"
    snapshot_root = tmp_path / "regime"
    signal_snapshot_root = tmp_path / "signals"
    events: list[str] = []

    def fake_refresh_regime_prices(
        *,
        start_date: date,
        end_date: date,
        price_root: Path,
    ) -> RegimePriceRefreshResult:
        assert start_date == date(2025, 11, 15)
        assert end_date == date(2026, 8, 29)
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
                    row_count=200,
                ),
            ),
            price_failures=(),
        )

    def fake_fetch_and_write_fred_series(
        *,
        series_ids: tuple[str, ...],
        start_date: date,
        end_date: date,
        output_root: Path,
    ) -> tuple[MarketSeriesFetchResult, ...]:
        assert events == ["prices"]
        assert series_ids == ("BAMLH0A0HYM2", "NFCI", "DGS10", "DGS2")
        assert start_date == date(2025, 11, 15)
        assert end_date == date(2026, 8, 29)
        assert output_root == market_series_root_arg
        events.append("market-series")
        return (
            MarketSeriesFetchResult(
                series_id="NFCI",
                source_series_id="NFCI",
                observation_path=output_root / "NFCI.jsonl",
                row_count=40,
                latest_observed_date=date(2026, 8, 26),
                latest_availability_date=date(2026, 8, 31),
            ),
        )

    def fake_compute_regime_backfill(
        *,
        start_date: date,
        end_date: date,
        price_root: Path,
        market_series_root: Path,
        snapshot_root: Path,
        signal_snapshot_root: Path,
        signal_time,
        snapshot_version: str | None,
        write_snapshot: bool,
        skip_existing: bool,
        overwrite_snapshot: bool,
    ) -> RegimeBackfillResult:
        assert events == ["prices", "market-series"]
        assert start_date == date(2026, 8, 28)
        assert end_date == date(2026, 8, 29)
        assert price_root == price_root_arg
        assert market_series_root == market_series_root_arg
        assert snapshot_root == snapshot_root_arg
        assert signal_snapshot_root == signal_snapshot_root_arg
        assert signal_time == "eod"
        assert snapshot_version is None
        assert write_snapshot is True
        assert skip_existing is True
        assert overwrite_snapshot is False
        events.append("backfill")
        return RegimeBackfillResult(
            start_date=start_date,
            end_date=end_date,
            source_dates=(date(2026, 8, 28), date(2026, 8, 29)),
            snapshot_paths=(
                snapshot_root / "2026-08-28.json",
                snapshot_root / "2026-08-29.json",
            ),
            signal_snapshot_paths=(
                signal_snapshot_root / "2026-08-28.jsonl",
                signal_snapshot_root / "2026-08-29.jsonl",
            ),
        )

    price_root_arg = price_root
    market_series_root_arg = market_series_root
    snapshot_root_arg = snapshot_root
    signal_snapshot_root_arg = signal_snapshot_root
    monkeypatch.setattr("marketlab.cli.refresh_regime_prices", fake_refresh_regime_prices)
    monkeypatch.setattr(
        "marketlab.cli.fetch_and_write_fred_series",
        fake_fetch_and_write_fred_series,
    )
    monkeypatch.setattr("marketlab.cli.compute_regime_backfill", fake_compute_regime_backfill)

    result = CliRunner().invoke(
        app,
        [
            "regime",
            "backfill",
            "--start",
            "2026-08-28",
            "--end",
            "2026-08-29",
            "--fetch-prices",
            "--fetch-market-series",
            "--lookback-days",
            "286",
            "--price-root",
            str(price_root),
            "--market-series-root",
            str(market_series_root),
            "--snapshot-root",
            str(snapshot_root),
            "--signal-root",
            str(signal_snapshot_root),
        ],
    )

    assert result.exit_code == 0
    assert events == ["prices", "market-series", "backfill"]
    assert "regime_price_symbols=SPY,QQQ" in result.output
    assert "market_series_ids=NFCI" in result.output
    assert "regime_backfill_date_count=2" in result.output
    assert "regime_backfill_first_date=2026-08-28" in result.output
    assert "regime_backfill_last_date=2026-08-29" in result.output
    assert "regime_snapshot_count=2" in result.output
    assert "market_signal_artifact_count=2" in result.output
    assert "regime_backfill_skipped_existing_count=0" in result.output
    assert str(snapshot_root / "2026-08-29.json") in result.output
    assert str(signal_snapshot_root / "2026-08-29.jsonl") in result.output


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


def test_regime_action_outcomes_outputs_frequency_and_summary_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_root = tmp_path / "regime"
    signal_root = tmp_path / "signals"
    price_root = tmp_path / "prices"

    def fake_compute_regime_action_outcomes(
        *,
        start_date: date,
        end_date: date,
        snapshot_root: Path,
        signal_snapshot_root: Path,
        price_root: Path,
        horizons: tuple[int, ...],
    ) -> RegimeActionOutcomeResult:
        assert start_date == date(2026, 1, 1)
        assert end_date == date(2026, 8, 28)
        assert snapshot_root == snapshot_root_arg
        assert signal_snapshot_root == signal_root_arg
        assert price_root == price_root_arg
        assert horizons == (20, 65)
        return RegimeActionOutcomeResult(
            start_date=start_date,
            end_date=end_date,
            actions=(
                RegimeActionState(
                    source_date=date(2026, 8, 1),
                    action_version="fixture",
                    state="scale_down_protect",
                    stretch_score=4,
                    washout_score=0,
                    confidence="high",
                    reason="fixture",
                    evidence=("fixture",),
                ),
            ),
            outcomes=(
                RegimeActionForwardOutcome(
                    source_date=date(2026, 8, 1),
                    price_date=date(2026, 8, 1),
                    action_state="scale_down_protect",
                    stretch_score=4,
                    washout_score=0,
                    action_confidence="high",
                    horizon_days=20,
                    spy_return=-0.02,
                    qqq_return=-0.04,
                    spy_max_drawdown=-0.06,
                    qqq_max_drawdown=-0.08,
                ),
            ),
            frequency_rows=(
                RegimeActionFrequencyRow(
                    action_state="scale_down_protect",
                    action_count=1,
                    share=1.0,
                ),
            ),
            summary_rows=(
                RegimeActionOutcomeSummaryRow(
                    bucket="action:scale_down_protect",
                    horizon_days=20,
                    action_count=1,
                    available_count=1,
                    avg_spy_return=-0.02,
                    avg_qqq_return=-0.04,
                    avg_spy_max_drawdown=-0.06,
                    avg_qqq_max_drawdown=-0.08,
                ),
            ),
            frequency_table="action_state        count\nscale_down_protect  1",
            table="bucket                     horizon\naction:scale_down_protect  20d",
        )

    snapshot_root_arg = snapshot_root
    signal_root_arg = signal_root
    price_root_arg = price_root
    monkeypatch.setattr(
        "marketlab.cli.compute_regime_action_outcomes",
        fake_compute_regime_action_outcomes,
    )

    result = CliRunner().invoke(
        app,
        [
            "regime",
            "action-outcomes",
            "--start",
            "2026-01-01",
            "--end",
            "2026-08-28",
            "--snapshot-root",
            str(snapshot_root),
            "--signal-root",
            str(signal_root),
            "--price-root",
            str(price_root),
            "--horizons",
            "20,65",
        ],
    )

    assert result.exit_code == 0
    assert "regime_action_count=1" in result.output
    assert "regime_action_outcome_count=1" in result.output
    assert "available_regime_action_outcome_count=1" in result.output
    assert "scale_down_protect  1" in result.output
    assert "action:scale_down_protect  20d" in result.output


def test_regime_pressure_outcomes_outputs_summary_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_root = tmp_path / "regime"
    signal_root = tmp_path / "signals"
    price_root = tmp_path / "prices"

    def fake_compute_regime_pressure_outcomes(
        *,
        start_date: date,
        end_date: date,
        snapshot_root: Path,
        signal_snapshot_root: Path,
        price_root: Path,
        horizons: tuple[int, ...],
    ) -> RegimePressureOutcomeResult:
        assert start_date == date(2026, 1, 1)
        assert end_date == date(2026, 8, 28)
        assert snapshot_root == snapshot_root_arg
        assert signal_snapshot_root == signal_root_arg
        assert price_root == price_root_arg
        assert horizons == (20, 65)
        return RegimePressureOutcomeResult(
            start_date=start_date,
            end_date=end_date,
            pressures=(
                RegimePressureSnapshot(
                    source_date=date(2026, 8, 1),
                    pressure_version="fixture",
                    stretch_pressure_score=0.91,
                    washout_pressure_score=0.05,
                    confidence="high",
                    features=(),
                ),
            ),
            outcomes=(
                RegimePressureForwardOutcome(
                    source_date=date(2026, 8, 1),
                    price_date=date(2026, 8, 1),
                    stretch_pressure_score=0.91,
                    washout_pressure_score=0.05,
                    stretch_pressure_percentile=0.96,
                    washout_pressure_percentile=0.20,
                    pressure_sample_count=200,
                    horizon_days=20,
                    spy_return=-0.02,
                    qqq_return=-0.04,
                    spy_max_drawdown=-0.06,
                    qqq_max_drawdown=-0.08,
                ),
            ),
            summary_rows=(
                RegimePressureOutcomeSummaryRow(
                    bucket="stretch:top_5",
                    horizon_days=20,
                    pressure_count=1,
                    available_count=1,
                    avg_stretch_pressure=0.91,
                    avg_washout_pressure=0.05,
                    avg_spy_return=-0.02,
                    avg_qqq_return=-0.04,
                    avg_spy_max_drawdown=-0.06,
                    avg_qqq_max_drawdown=-0.08,
                ),
            ),
            table="bucket         horizon\nstretch:top_5  20d",
        )

    snapshot_root_arg = snapshot_root
    signal_root_arg = signal_root
    price_root_arg = price_root
    monkeypatch.setattr(
        "marketlab.cli.compute_regime_pressure_outcomes",
        fake_compute_regime_pressure_outcomes,
    )

    result = CliRunner().invoke(
        app,
        [
            "regime",
            "pressure-outcomes",
            "--start",
            "2026-01-01",
            "--end",
            "2026-08-28",
            "--snapshot-root",
            str(snapshot_root),
            "--signal-root",
            str(signal_root),
            "--price-root",
            str(price_root),
            "--horizons",
            "20,65",
        ],
    )

    assert result.exit_code == 0
    assert "regime_pressure_count=1" in result.output
    assert "regime_pressure_outcome_count=1" in result.output
    assert "available_regime_pressure_outcome_count=1" in result.output
    assert "stretch:top_5  20d" in result.output


def test_regime_signal_outcomes_outputs_summary_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signal_root = tmp_path / "signals"
    price_root = tmp_path / "prices"

    def fake_compute_market_signal_outcomes(
        *,
        start_date: date,
        end_date: date,
        signal_snapshot_root: Path,
        price_root: Path,
        horizons: tuple[int, ...],
    ) -> MarketSignalOutcomeResult:
        assert start_date == date(2026, 1, 1)
        assert end_date == date(2026, 8, 28)
        assert signal_snapshot_root == signal_root_arg
        assert price_root == price_root_arg
        assert horizons == (20, 65)
        return MarketSignalOutcomeResult(
            start_date=start_date,
            end_date=end_date,
            outcomes=(
                MarketSignalForwardOutcome(
                    source_date=date(2026, 8, 1),
                    family="volatility",
                    name="vol_of_vol",
                    status="calm",
                    score=1,
                    horizon_days=20,
                    spy_return=0.05,
                    qqq_return=0.08,
                    spy_max_drawdown=-0.02,
                    qqq_max_drawdown=-0.03,
                ),
            ),
            summary_rows=(
                MarketSignalOutcomeSummaryRow(
                    bucket="signal:volatility/vol_of_vol/calm",
                    horizon_days=20,
                    signal_count=1,
                    available_count=1,
                    avg_spy_return=0.05,
                    avg_qqq_return=0.08,
                    avg_spy_max_drawdown=-0.02,
                    avg_qqq_max_drawdown=-0.03,
                ),
            ),
            table=(
                "bucket                              horizon\n"
                "signal:volatility/vol_of_vol/calm  20d"
            ),
        )

    signal_root_arg = signal_root
    price_root_arg = price_root
    monkeypatch.setattr(
        "marketlab.cli.compute_market_signal_outcomes",
        fake_compute_market_signal_outcomes,
    )

    result = CliRunner().invoke(
        app,
        [
            "regime",
            "signal-outcomes",
            "--start",
            "2026-01-01",
            "--end",
            "2026-08-28",
            "--signal-root",
            str(signal_root),
            "--price-root",
            str(price_root),
            "--horizons",
            "20,65",
        ],
    )

    assert result.exit_code == 0
    assert "market_signal_outcome_count=1" in result.output
    assert "available_market_signal_outcome_count=1" in result.output
    assert "signal:volatility/vol_of_vol/calm  20d" in result.output


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
        signal_time,
        snapshot_version: str | None,
        write_snapshot: bool,
    ) -> CandidateValidationResult:
        assert source_date == date(2026, 8, 26)
        assert limit == 5
        assert min_dollar_volume == 10_000_000.0
        assert signal_time == "eod"
        assert snapshot_version is None
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
        observations_root: Path,
        regime_snapshot_root: Path | None,
        horizons: tuple[int, ...],
    ) -> CandidateOutcomeResult:
        assert start_date == date(2026, 1, 1)
        assert end_date == date(2026, 8, 26)
        assert observations_root == tmp_path / "observations" / "bulltard"
        assert regime_snapshot_root == tmp_path / "regime"
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
            "--observations-root",
            str(tmp_path / "observations" / "bulltard"),
            "--regime-root",
            str(tmp_path / "regime"),
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
        observations_root: Path,
        regime_snapshot_root: Path | None,
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

    def fake_validate_bulltard_candidates(
        *,
        source_date: date,
        observations_root: Path,
        price_root: Path,
        snapshot_root: Path,
        limit: int,
        min_dollar_volume: float,
        signal_time,
        snapshot_version: str | None,
        write_snapshot: bool,
    ) -> CandidateValidationResult:
        assert events == ["capture", "candidate_prices"]
        assert observations_root == output_root
        assert price_root == price_root_arg
        assert snapshot_root == snapshot_root_arg
        assert limit == 12
        assert signal_time == "eod"
        assert snapshot_version is None
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
        observations_root: Path,
        regime_snapshot_root: Path | None,
        horizons: tuple[int, ...],
    ) -> CandidateOutcomeResult:
        assert events == ["capture", "candidate_prices", "validate"]
        assert start_date == date(2026, 8, 1)
        assert end_date == date(2026, 8, 26)
        assert snapshot_root == snapshot_root_arg
        assert price_root == price_root_arg
        assert observations_root == output_root
        assert regime_snapshot_root is None
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

    price_root_arg = price_root
    snapshot_root_arg = snapshot_root
    snapshot_root.mkdir(parents=True)
    (snapshot_root / "2026-08-01.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr("marketlab.cli.run_daily_workflow", fake_run_daily_workflow)
    monkeypatch.setattr(
        "marketlab.cli.refresh_candidate_price_set",
        fake_refresh_candidate_price_set,
    )
    monkeypatch.setattr(
        "marketlab.cli.validate_bulltard_candidates",
        fake_validate_bulltard_candidates,
    )
    monkeypatch.setattr("marketlab.cli.compute_bulltard_outcomes", fake_compute_bulltard_outcomes)

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
    assert events == ["capture", "candidate_prices", "validate", "candidate_outcomes"]
    assert "price_symbols=META,SPY" in result.output
    assert "price_success_count=2" in result.output
    assert "regime_price_symbols" not in result.output
    assert "regime_snapshot_path" not in result.output
    assert "candidate_validation_count=1" in result.output
    assert "candidate_validation_summary=candidates:1 confirm:1 watch:0 avoid:0" in result.output
    assert "META    confirm" in result.output
    assert "outcome_count=1" in result.output
    assert "available_outcome_count=1" in result.output
    assert "all     1d" in result.output


def test_bulltard_daily_rejects_regime_option() -> None:
    result = CliRunner().invoke(
        app,
        [
            "bulltard",
            "daily",
            str(FIXTURE_DIR / "recap_with_trades_of_interest.html"),
            "--date",
            "2026-08-26",
            "--regime",
        ],
    )

    assert result.exit_code != 0
    assert "No such option: --regime" in result.output


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
        vvix_close=85.0,
    )


def _portfolio_policy_snapshot(*, source_date: date) -> PortfolioPolicySnapshot:
    return PortfolioPolicySnapshot(
        source_date=source_date,
        policy_version="fixture_policy",
        regime="risk_on",
        regime_score=5,
        regime_confidence="high",
        regime_price_date=source_date,
        regime_action_state="no_change",
        regime_action_confidence="medium",
        regime_action_reason="fixture action",
        stretch_score=1,
        washout_score=0,
        stretch_pressure_score=0.30,
        washout_pressure_score=0.20,
        pressure_confidence="medium",
        policy_state="maintain",
        policy_confidence="medium",
        marginal_beta_target=1.0,
        marginal_beta_range="0.95-1.05 tactical beta",
        cash_posture="maintain dry powder",
        long_delta_stance="no forced change",
        overlay_stance="selective only",
        put_underwriting_stance="selective only",
        single_name_risk_budget="normal",
        candidate_count=0,
        confirm_candidate_count=0,
        watch_candidate_count=0,
        avoid_candidate_count=0,
        candidate_highlights=(),
        rationale=("fixture rationale",),
    )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
