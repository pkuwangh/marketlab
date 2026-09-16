"""Command-line entrypoint for MarketLab."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from pathlib import Path

import typer
from loguru import logger

from marketlab import __version__
from marketlab.bulltard.candidates import (
    CandidateReviewError,
    format_candidate_reviews,
    load_candidate_reviews,
)
from marketlab.bulltard.daily import (
    CandidatePriceRefreshResult,
    DailyWorkflowError,
    DailyWorkflowResult,
    run_daily_workflow,
)
from marketlab.bulltard.daily import (
    refresh_candidate_prices as refresh_candidate_price_set,
)
from marketlab.bulltard.ingest import (
    DEFAULT_DEBUG_ROOT,
    DEFAULT_OBSERVATIONS_ROOT,
    IngestError,
    build_ingest_plan,
    ingest_planned_view,
    ingest_ticker_page,
    ingest_trades_of_interest,
)
from marketlab.bulltard.models import BulltardView
from marketlab.bulltard.outcomes import (
    CandidateOutcomeError,
    CandidateOutcomeResult,
    compute_bulltard_outcomes,
)
from marketlab.bulltard.recaps import (
    SignedSourceUrlError,
    extract_signed_source_url,
    redact_capability_url,
)
from marketlab.bulltard.validation import (
    CANDIDATE_VALIDATION_SNAPSHOT_FILENAME,
    DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
    DEFAULT_MIN_DOLLAR_VOLUME,
    CandidateValidationError,
    CandidateValidationSummary,
    validate_bulltard_candidates,
)
from marketlab.gmail import (
    DEFAULT_GMAIL_CLIENT_SECRET_PATH,
    DEFAULT_GMAIL_RECAP_CACHE_ROOT,
    DEFAULT_GMAIL_TOKEN_PATH,
    GmailError,
    fetch_bulltard_recap_from_gmail,
    gmail_credentials_available,
    run_gmail_oauth_flow,
)
from marketlab.logging import configure_logging
from marketlab.market_series import (
    DEFAULT_FRED_MARKET_SERIES_IDS,
    DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
    MarketSeriesError,
    MarketSeriesFetchResult,
    fetch_and_write_fred_series,
)
from marketlab.market_signals import DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT
from marketlab.policy import (
    DEFAULT_POLICY_SNAPSHOT_ROOT,
    DailyPolicyReportResult,
    PortfolioPolicyBackfillResult,
    PortfolioPolicyError,
    PortfolioPolicyOutcomeResult,
    PortfolioPolicySnapshotResult,
    compute_daily_policy_report,
    compute_portfolio_policy_backfill,
    compute_portfolio_policy_outcomes,
    compute_portfolio_policy_snapshot,
)
from marketlab.prices import (
    DEFAULT_PRICE_OBSERVATIONS_ROOT,
    PriceDataError,
    fetch_and_write_cboe_index_daily_prices,
    fetch_and_write_stooq_daily_prices,
    fetch_and_write_yahoo_daily_prices,
    import_daily_price_csv,
)
from marketlab.regime import (
    DEFAULT_REGIME_SNAPSHOT_ROOT,
    REGIME_KEY_SIGNALS_CAPTION,
    REGIME_MARKET_SIGNALS_CAPTION,
    MarketSignalOutcomeResult,
    RegimeActionOutcomeResult,
    RegimeBackfillResult,
    RegimeCorrectionEpisodeResult,
    RegimeError,
    RegimeOutcomeResult,
    RegimePostureOutcomeResult,
    RegimePressureOutcomeResult,
    RegimePriceRefreshResult,
    RegimeProtectClusterResult,
    RegimeProtectOutcomeResult,
    RegimeRecentReportResult,
    RegimeRedeployOutcomeResult,
    RegimeSnapshotResult,
    compute_market_signal_outcomes,
    compute_regime_action_outcomes,
    compute_regime_backfill,
    compute_regime_correction_episodes,
    compute_regime_outcomes,
    compute_regime_posture_outcomes,
    compute_regime_pressure_outcomes,
    compute_regime_protect_clusters,
    compute_regime_protect_outcomes,
    compute_regime_recent_report,
    compute_regime_redeploy_outcomes,
    compute_regime_snapshot,
    format_regime_key_signals,
    refresh_regime_prices,
)
from marketlab.regime_export import (
    RegimeExportError,
    RegimeExportResult,
    export_regime_workbook,
    regime_export_paths,
    regime_outcome_report_path,
)
from marketlab.snapshots.models import SignalTime, snapshot_source_dates
from marketlab.store import (
    DEFAULT_RESEARCH_DB_PATH,
    ResearchStoreError,
    StoreRefreshResult,
    format_query_result,
    format_store_refresh_result,
    query_research_store,
    refresh_research_store,
    summarize_research_store,
)
from marketlab.versions import (
    BULLTARD_SNAPSHOT_VERSION,
    POLICY_SNAPSHOT_VERSION,
    REGIME_SNAPSHOT_VERSION,
)


class LogLevel(StrEnum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class RegimeOutcomeGroup(StrEnum):
    REGIME = "regime"
    SIGNAL = "signal"
    ACTION = "action"
    PRESSURE = "pressure"
    EPISODE = "episode"
    POSTURE = "posture"
    REDEPLOY = "redeploy"
    PROTECT = "protect"
    POLICY = "policy"


app = typer.Typer(
    help="MarketLab research workflow CLI.",
    no_args_is_help=True,
)
bulltard_app = typer.Typer(
    help="Bulltard option-flow and single-name candidate pillar.",
    no_args_is_help=True,
)
data_app = typer.Typer(
    help="Raw data download/import and local query-store utilities.",
    no_args_is_help=True,
)
prices_app = typer.Typer(
    help="Daily OHLCV price utilities.",
    no_args_is_help=True,
)
market_series_app = typer.Typer(
    help="Scalar market series utilities.",
    no_args_is_help=True,
)
tools_app = typer.Typer(
    help="External integration and one-off helper utilities.",
    no_args_is_help=True,
)
gmail_app = typer.Typer(
    help="Find Bulltard recap emails in Gmail and cache them for daily ingest.",
    no_args_is_help=True,
)
regime_app = typer.Typer(
    help="Market regime pillar.",
    no_args_is_help=True,
)
store_app = typer.Typer(
    help="Local research store utilities.",
    no_args_is_help=True,
)
app.add_typer(bulltard_app, name="bulltard")
app.add_typer(data_app, name="data")
app.add_typer(regime_app, name="regime")
app.add_typer(tools_app, name="tools")
data_app.add_typer(prices_app, name="prices")
data_app.add_typer(market_series_app, name="market-series")
data_app.add_typer(store_app, name="store")
tools_app.add_typer(gmail_app, name="gmail")

DEFAULT_DAILY_PRICE_LOOKBACK_DAYS = 550
DEFAULT_OUTCOME_HORIZONS_VALUE = "1,5,20,40,65,126"
DEFAULT_BULLTARD_INBOX_ROOT = Path("data/inbox/bulltard")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"marketlab {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    log_level: LogLevel = typer.Option(
        LogLevel.INFO,
        "--log-level",
        envvar="MARKETLAB_LOG_LEVEL",
        case_sensitive=False,
        help="Set CLI log verbosity.",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the application version and exit.",
    ),
) -> None:
    """Run MarketLab research workflows."""
    configure_logging(log_level.value)


@gmail_app.command("auth", no_args_is_help=True)
def gmail_auth(
    client_secret_path: Path = typer.Option(
        DEFAULT_GMAIL_CLIENT_SECRET_PATH,
        "--client-secret",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "Path to the Google OAuth Desktop app JSON downloaded from Google Cloud; "
            "not your Gmail password."
        ),
    ),
    token_path: Path = typer.Option(
        DEFAULT_GMAIL_TOKEN_PATH,
        "--token",
        dir_okay=False,
        help=(
            "Local file this command creates for Gmail access and refresh tokens; "
            "keep it under secrets/."
        ),
    ),
    port: int = typer.Option(
        0,
        "--port",
        min=0,
        help=(
            "Local 127.0.0.1 OAuth callback port. 0 picks a free port; "
            "set a fixed port for SSH forwarding."
        ),
    ),
    open_browser: bool = typer.Option(
        True,
        "--browser/--no-browser",
        help=(
            "Open the Google consent page automatically. Use --no-browser on SSH/headless machines."
        ),
    ),
    timeout_seconds: int = typer.Option(
        300,
        "--timeout-seconds",
        min=1,
        help="Seconds to wait for Google to redirect back to the local callback.",
    ),
) -> None:
    """Authorize read-only Gmail access and write the local token file.

    Run this once after placing the Google OAuth desktop-client JSON at --client-secret.
    Use --no-browser --port PORT on SSH/headless machines and open the printed URL from
    a browser that can reach 127.0.0.1:PORT on the machine running MarketLab.
    """

    try:
        result = run_gmail_oauth_flow(
            client_secret_path=client_secret_path,
            token_path=token_path,
            port=port,
            open_browser=open_browser,
            timeout_seconds=timeout_seconds,
            auth_url_callback=lambda url: typer.echo(f"authorization_url={url}"),
        )
    except GmailError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"gmail_token_path={result.token_path}")
    typer.echo(f"gmail_scope={result.scope}")
    typer.echo(f"gmail_token_expires_at={result.expires_at or ''}")


@gmail_app.command("bulltard-recap", no_args_is_help=True)
def gmail_bulltard_recap(
    source_date_value: str = typer.Option(
        ...,
        "--date",
        metavar="YYYY-MM-DD",
        help="Bulltard recap date to fetch from Gmail.",
    ),
    client_secret_path: Path = typer.Option(
        DEFAULT_GMAIL_CLIENT_SECRET_PATH,
        "--client-secret",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "Path to the Google OAuth Desktop app JSON downloaded from Google Cloud; "
            "used to refresh tokens when needed."
        ),
    ),
    token_path: Path = typer.Option(
        DEFAULT_GMAIL_TOKEN_PATH,
        "--token",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Existing local Gmail token created by marketlab tools gmail auth.",
    ),
    output_root: Path = typer.Option(
        DEFAULT_GMAIL_RECAP_CACHE_ROOT,
        "--output-root",
        file_okay=False,
        help="Root directory for cached recap files; created automatically when needed.",
    ),
    query: str | None = typer.Option(
        None,
        "--query",
        help="Override the default Gmail search query; default tries Bulltard/date terms.",
    ),
    max_results: int = typer.Option(
        10,
        "--max-results",
        min=1,
        help="Maximum matching Gmail messages to inspect for a valid recap.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Replace an existing cached recap for the same date.",
    ),
) -> None:
    """Fetch the Bulltard recap email from Gmail and cache it for Bulltard ingest."""

    source_date = _parse_source_date(source_date_value)
    try:
        result = fetch_bulltard_recap_from_gmail(
            source_date=source_date,
            client_secret_path=client_secret_path,
            token_path=token_path,
            output_root=output_root,
            query=query,
            max_results=max_results,
            overwrite=overwrite,
        )
    except GmailError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"gmail_recap_path={result.recap_path}")
    typer.echo(f"gmail_message_id={result.message_id}")
    typer.echo(f"gmail_thread_id={result.thread_id or ''}")
    typer.echo(f"gmail_subject={result.subject or ''}")
    typer.echo(f"gmail_from={result.sender or ''}")
    typer.echo(f"gmail_received_at={result.received_at or ''}")
    typer.echo(f"gmail_query={result.query}")


@app.command("daily")
def daily_run(
    source_date_value: str | None = typer.Option(
        None,
        "--date",
        metavar="YYYY-MM-DD",
        help="Daily research date. Defaults to the local current date.",
    ),
    recap_path: Path | None = typer.Option(
        None,
        "--recap",
        dir_okay=False,
        readable=True,
        help=(
            "Optional Bulltard recap file. Defaults to "
            "data/inbox/bulltard/recap-DATE.html when present."
        ),
    ),
    run_bulltard_flag: bool = typer.Option(
        True,
        "--bulltard/--no-bulltard",
        help="Capture and validate Bulltard candidates when a recap file is available.",
    ),
    use_gmail_flag: bool = typer.Option(
        True,
        "--gmail/--no-gmail",
        help="Fetch the Bulltard recap from Gmail when no local recap file is present.",
    ),
    require_recap: bool = typer.Option(
        False,
        "--require-recap",
        help="Fail if Bulltard is enabled but no recap file is available.",
    ),
    refresh_prices_flag: bool = typer.Option(
        True,
        "--prices/--no-prices",
        help="Refresh market price sources before computing daily outputs.",
    ),
    refresh_market_series_flag: bool = typer.Option(
        True,
        "--market-series/--no-market-series",
        help="Refresh FRED market series before computing the regime snapshot.",
    ),
    fetch_ticker_details: bool = typer.Option(
        True,
        "--ticker-details/--no-ticker-details",
        help="Fetch Bulltard ticker detail pages for selected candidates.",
    ),
    top_ranked: int = typer.Option(
        0,
        "--top-ranked",
        min=0,
        help="Also fetch ticker details for the top N ranked database names.",
    ),
    extra_tickers_value: str = typer.Option(
        "",
        "--ticker",
        help="Comma-separated extra Bulltard ticker symbols to fetch details for.",
    ),
    limit: int = typer.Option(
        12,
        "--limit",
        min=1,
        help="Maximum number of candidates to validate and show.",
    ),
    min_dollar_volume: float = typer.Option(
        DEFAULT_MIN_DOLLAR_VOLUME,
        "--min-dollar-volume",
        min=0.0,
        help="Minimum daily dollar volume for the candidate liquidity gate.",
    ),
    compute_outcomes_flag: bool = typer.Option(
        True,
        "--outcomes/--no-outcomes",
        help="Replay candidate outcomes after validation when Bulltard runs.",
    ),
    refresh_store_flag: bool = typer.Option(
        True,
        "--store/--no-store",
        help="Refresh the local DuckDB research store.",
    ),
    strict_optional_stages: bool = typer.Option(
        False,
        "--strict",
        help="Fail instead of warning when optional refresh/store stages fail.",
    ),
    price_start_value: str | None = typer.Option(
        None,
        "--price-start",
        metavar="YYYY-MM-DD",
        help=(
            "First price date for refreshes. "
            f"Defaults to {DEFAULT_DAILY_PRICE_LOOKBACK_DAYS} days before --date."
        ),
    ),
    price_end_value: str | None = typer.Option(
        None,
        "--price-end",
        metavar="YYYY-MM-DD",
        help="Last price date for refreshes. Defaults to --date.",
    ),
    market_series_start_value: str | None = typer.Option(
        None,
        "--market-series-start",
        metavar="YYYY-MM-DD",
        help=(
            "First market series date for refresh. "
            f"Defaults to {DEFAULT_DAILY_PRICE_LOOKBACK_DAYS} days before --date."
        ),
    ),
    market_series_end_value: str | None = typer.Option(
        None,
        "--market-series-end",
        metavar="YYYY-MM-DD",
        help="Last market series date for refresh. Defaults to --date.",
    ),
    price_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--price-root",
        file_okay=False,
        help="Root directory containing daily price observations.",
    ),
    market_series_root: Path = typer.Option(
        DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
        "--market-series-root",
        file_okay=False,
        help="Root directory containing scalar market series observations.",
    ),
    bulltard_observation_root: Path = typer.Option(
        DEFAULT_OBSERVATIONS_ROOT,
        "--bulltard-root",
        file_okay=False,
        help="Root directory for structured Bulltard observations.",
    ),
    bulltard_debug_root: Path = typer.Option(
        DEFAULT_DEBUG_ROOT,
        "--bulltard-debug-root",
        file_okay=False,
        help="Root directory for Bulltard parser debug payloads.",
    ),
    gmail_client_secret_path: Path = typer.Option(
        DEFAULT_GMAIL_CLIENT_SECRET_PATH,
        "--gmail-client-secret",
        dir_okay=False,
        help=(
            "Google OAuth Desktop app JSON path for automatic Gmail recap fetch; "
            "not your Gmail password."
        ),
    ),
    gmail_token_path: Path = typer.Option(
        DEFAULT_GMAIL_TOKEN_PATH,
        "--gmail-token",
        dir_okay=False,
        help="Local Gmail token path created by marketlab tools gmail auth.",
    ),
    gmail_query: str | None = typer.Option(
        None,
        "--gmail-query",
        help="Override the default Gmail search query used by --gmail.",
    ),
    regime_snapshot_root: Path = typer.Option(
        DEFAULT_REGIME_SNAPSHOT_ROOT,
        "--regime-root",
        file_okay=False,
        help="Root directory for market regime snapshots.",
    ),
    market_signal_snapshot_root: Path = typer.Option(
        DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
        "--signal-root",
        file_okay=False,
        help="Root directory for market signal snapshots.",
    ),
    candidate_snapshot_root: Path = typer.Option(
        DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
        "--candidate-root",
        file_okay=False,
        help="Root directory for Bulltard candidate validation snapshots.",
    ),
    policy_snapshot_root: Path = typer.Option(
        DEFAULT_POLICY_SNAPSHOT_ROOT,
        "--policy-root",
        file_okay=False,
        help="Root directory for portfolio policy snapshots.",
    ),
    db_path: Path = typer.Option(
        DEFAULT_RESEARCH_DB_PATH,
        "--db",
        dir_okay=False,
        help="DuckDB research store path.",
    ),
    signal_time: SignalTime = typer.Option(
        SignalTime.EOD,
        "--signal-time",
        help="Signal timing label. Regime date-level workflows currently support only eod.",
    ),
) -> None:
    """Run the normal daily MarketLab research cycle."""

    source_date = _parse_source_date(source_date_value) if source_date_value else date.today()
    price_start = (
        _parse_date_option(price_start_value, option_name="--price-start")
        if price_start_value
        else source_date - timedelta(days=DEFAULT_DAILY_PRICE_LOOKBACK_DAYS)
    )
    price_end = (
        _parse_date_option(price_end_value, option_name="--price-end")
        if price_end_value
        else source_date
    )
    market_series_start = (
        _parse_date_option(market_series_start_value, option_name="--market-series-start")
        if market_series_start_value
        else source_date - timedelta(days=DEFAULT_DAILY_PRICE_LOOKBACK_DAYS)
    )
    market_series_end = (
        _parse_date_option(market_series_end_value, option_name="--market-series-end")
        if market_series_end_value
        else source_date
    )
    resolved_recap_path = recap_path or _default_recap_path(source_date)

    typer.echo(f"daily_date={source_date.isoformat()}")
    typer.echo(f"signal_time={signal_time}")
    typer.echo(f"regime_snapshot_version={REGIME_SNAPSHOT_VERSION}")
    typer.echo(f"bulltard_snapshot_version={BULLTARD_SNAPSHOT_VERSION}")
    typer.echo(f"policy_snapshot_version={POLICY_SNAPSHOT_VERSION}")
    typer.echo("")

    if refresh_prices_flag:
        typer.echo("[regime-source-refresh]")
        try:
            price_refresh_result = refresh_regime_prices(
                start_date=price_start,
                end_date=price_end,
                price_root=price_root,
            )
        except RegimeError as exc:
            _handle_optional_daily_error(
                "regime_price_refresh",
                exc,
                strict=strict_optional_stages,
            )
        else:
            typer.echo(f"regime_price_success_count={len(price_refresh_result.price_results)}")
            typer.echo(f"regime_price_failure_count={len(price_refresh_result.price_failures)}")
        typer.echo("")

    if refresh_market_series_flag:
        typer.echo("[market-series-refresh]")
        try:
            market_series_results = fetch_and_write_fred_series(
                series_ids=DEFAULT_FRED_MARKET_SERIES_IDS,
                start_date=market_series_start,
                end_date=market_series_end,
                output_root=market_series_root,
            )
        except MarketSeriesError as exc:
            _handle_optional_daily_error(
                "market_series_refresh",
                exc,
                strict=strict_optional_stages,
            )
        else:
            typer.echo(f"market_series_success_count={len(market_series_results)}")
        typer.echo("")

    typer.echo("[regime]")
    try:
        regime_result = compute_regime_snapshot(
            source_date=source_date,
            price_root=price_root,
            market_series_root=market_series_root,
            snapshot_root=regime_snapshot_root,
            signal_snapshot_root=market_signal_snapshot_root,
            signal_time=signal_time,
            snapshot_version=None,
            write_snapshot=True,
            overwrite_snapshot=True,
            require_action_history=True,
        )
    except RegimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if regime_result.snapshot_path is not None:
        typer.echo(f"regime_snapshot_path={regime_result.snapshot_path}")
    if regime_result.signal_snapshot_path is not None:
        typer.echo(f"market_signal_snapshot_path={regime_result.signal_snapshot_path}")
    typer.echo(f"regime={regime_result.snapshot.regime}")
    typer.echo(f"action_state={regime_result.snapshot.action_state}")
    typer.echo(f"regime_confidence={regime_result.snapshot.confidence}")
    typer.echo("")

    bulltard_ran = False
    if run_bulltard_flag:
        typer.echo("[bulltard]")
        if (
            recap_path is None
            and not resolved_recap_path.is_file()
            and use_gmail_flag
            and gmail_credentials_available(
                client_secret_path=gmail_client_secret_path,
                token_path=gmail_token_path,
            )
        ):
            try:
                gmail_result = fetch_bulltard_recap_from_gmail(
                    source_date=source_date,
                    client_secret_path=gmail_client_secret_path,
                    token_path=gmail_token_path,
                    output_root=DEFAULT_GMAIL_RECAP_CACHE_ROOT,
                    query=gmail_query,
                )
            except GmailError as exc:
                if require_recap:
                    raise typer.BadParameter(str(exc), param_hint="--gmail") from exc
                _handle_optional_daily_error(
                    "gmail_bulltard_recap",
                    exc,
                    strict=strict_optional_stages,
                )
            else:
                resolved_recap_path = gmail_result.recap_path
                typer.echo(f"gmail_recap_path={gmail_result.recap_path}")
                typer.echo(f"gmail_message_id={gmail_result.message_id}")
        elif recap_path is None and not resolved_recap_path.is_file() and use_gmail_flag:
            typer.echo("gmail_status=skipped_missing_credentials")

        if not resolved_recap_path.is_file():
            if recap_path is not None or require_recap:
                raise typer.BadParameter(
                    f"Bulltard recap file not found: {resolved_recap_path}",
                    param_hint="--recap",
                )
            typer.echo("bulltard_status=skipped_missing_recap")
            typer.echo(f"expected_recap_path={resolved_recap_path}")
            typer.echo("")
        else:
            bulltard_ran = True
            try:
                bulltard_result = run_daily_workflow(
                    source_date=source_date,
                    recap_path=resolved_recap_path,
                    output_root=bulltard_observation_root,
                    debug_root=bulltard_debug_root,
                    fetch_ticker_details=fetch_ticker_details,
                    top_ranked=top_ranked,
                    extra_tickers=_parse_extra_tickers(extra_tickers_value),
                    limit=limit,
                )
            except DailyWorkflowError as exc:
                raise typer.BadParameter(str(exc)) from exc
            _echo_bulltard_daily_capture_summary(bulltard_result)
            typer.echo("")

            if refresh_prices_flag:
                try:
                    candidate_price_result = refresh_candidate_price_set(
                        source_date=source_date,
                        start_date=price_start,
                        end_date=price_end,
                        observations_root=bulltard_observation_root,
                        price_root=price_root,
                        limit=limit,
                    )
                except DailyWorkflowError as exc:
                    _handle_optional_daily_error(
                        "candidate_price_refresh",
                        exc,
                        strict=strict_optional_stages,
                    )
                else:
                    typer.echo(
                        f"candidate_price_success_count={len(candidate_price_result.price_results)}"
                    )
                    typer.echo(
                        f"candidate_price_failure_count={len(candidate_price_result.price_failures)}"
                    )
                    typer.echo("")

            try:
                validation_result = validate_bulltard_candidates(
                    source_date=source_date,
                    observations_root=bulltard_observation_root,
                    price_root=price_root,
                    snapshot_root=candidate_snapshot_root,
                    limit=limit,
                    min_dollar_volume=min_dollar_volume,
                    signal_time=signal_time,
                    snapshot_version=None,
                    write_snapshot=True,
                )
            except CandidateValidationError as exc:
                raise typer.BadParameter(str(exc)) from exc
            if validation_result.snapshot_path is not None:
                typer.echo(f"candidate_validation_snapshot_path={validation_result.snapshot_path}")
            typer.echo(f"candidate_validation_count={len(validation_result.snapshots)}")
            typer.echo(
                _format_validation_summary(
                    validation_result.summary,
                    prefix="candidate_validation_summary",
                )
            )
            typer.echo("")
            typer.echo(validation_result.table)
            typer.echo("")

            if compute_outcomes_flag:
                outcome_start = _default_outcome_start(
                    snapshot_root=candidate_snapshot_root,
                    fallback=source_date,
                )
                try:
                    outcome_result = compute_bulltard_outcomes(
                        start_date=outcome_start,
                        end_date=source_date,
                        snapshot_root=candidate_snapshot_root,
                        price_root=price_root,
                        observations_root=bulltard_observation_root,
                        regime_snapshot_root=regime_snapshot_root,
                        horizons=_parse_horizons(DEFAULT_OUTCOME_HORIZONS_VALUE),
                    )
                except CandidateOutcomeError as exc:
                    _handle_optional_daily_error(
                        "candidate_outcomes",
                        exc,
                        strict=strict_optional_stages,
                    )
                else:
                    typer.echo(f"candidate_outcome_count={len(outcome_result.outcomes)}")
                    typer.echo(
                        "candidate_available_outcome_count="
                        f"{_available_candidate_outcome_count(outcome_result)}"
                    )
                    typer.echo("")

    typer.echo("[report]")
    try:
        report_result = compute_daily_policy_report(
            source_date=source_date,
            regime_snapshot_root=regime_snapshot_root,
            market_signal_snapshot_root=market_signal_snapshot_root,
            candidate_snapshot_root=candidate_snapshot_root,
            policy_snapshot_root=policy_snapshot_root,
            signal_time=signal_time,
            snapshot_version=None,
            write_snapshot=True,
        )
    except PortfolioPolicyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _echo_daily_policy_report_result(report_result)
    typer.echo("")

    if refresh_store_flag:
        typer.echo("[store]")
        try:
            store_result = refresh_research_store(
                db_path=db_path,
                price_root=price_root,
                market_series_root=market_series_root,
                regime_snapshot_root=regime_snapshot_root,
                market_signal_snapshot_root=market_signal_snapshot_root,
                candidate_snapshot_root=candidate_snapshot_root,
                policy_snapshot_root=policy_snapshot_root,
                bulltard_observation_root=bulltard_observation_root,
            )
        except ResearchStoreError as exc:
            _handle_optional_daily_error("store_refresh", exc, strict=strict_optional_stages)
        else:
            typer.echo(f"research_db_path={store_result.db_path}")
            typer.echo(f"research_store_schema={store_result.schema_version}")
            typer.echo(f"research_store_table_count={len(store_result.table_refreshes)}")
        typer.echo("")

    typer.echo("daily_status=complete")
    typer.echo(f"bulltard_ran={str(bulltard_ran).lower()}")


@prices_app.command("fetch", no_args_is_help=True)
def prices_fetch(
    symbols_value: str = typer.Argument(
        ...,
        metavar="SYMBOL[,SYMBOL...]",
        help="Comma-separated ticker symbols to fetch.",
    ),
    start_date_value: str = typer.Option(
        ...,
        "--start",
        metavar="YYYY-MM-DD",
        help="First price date to fetch.",
    ),
    end_date_value: str = typer.Option(
        ...,
        "--end",
        metavar="YYYY-MM-DD",
        help="Last price date to fetch.",
    ),
    output_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--output-root",
        file_okay=False,
        help="Root directory for daily price observations.",
    ),
    stooq_api_key: str | None = typer.Option(
        None,
        "--stooq-api-key",
        envvar="MARKETLAB_STOOQ_API_KEY",
        help="Optional Stooq API key.",
    ),
) -> None:
    """Fetch daily OHLCV observations."""

    start_date = _parse_date_option(start_date_value, option_name="--start")
    end_date = _parse_date_option(end_date_value, option_name="--end")
    try:
        results = fetch_and_write_stooq_daily_prices(
            symbols=_parse_symbols(symbols_value),
            start_date=start_date,
            end_date=end_date,
            output_root=output_root,
            api_key=stooq_api_key,
        )
    except PriceDataError as exc:
        raise typer.BadParameter(str(exc)) from exc

    for result in results:
        typer.echo(
            f"symbol={result.symbol} source_symbol={result.source_symbol} "
            f"row_count={result.row_count} observation_path={result.observation_path}"
        )
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        symbol_count=len(results),
        output_root=str(output_root),
    ).success("Fetched daily price observations")


@prices_app.command("fetch-yahoo", no_args_is_help=True)
def prices_fetch_yahoo(
    symbols_value: str = typer.Argument(
        ...,
        metavar="SYMBOL[,SYMBOL...]",
        help="Comma-separated ticker symbols to fetch.",
    ),
    start_date_value: str = typer.Option(
        ...,
        "--start",
        metavar="YYYY-MM-DD",
        help="First price date to fetch.",
    ),
    end_date_value: str = typer.Option(
        ...,
        "--end",
        metavar="YYYY-MM-DD",
        help="Last price date to fetch.",
    ),
    output_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--output-root",
        file_okay=False,
        help="Root directory for daily price observations.",
    ),
) -> None:
    """Fetch daily OHLCV observations from Yahoo Finance through yfinance."""

    start_date = _parse_date_option(start_date_value, option_name="--start")
    end_date = _parse_date_option(end_date_value, option_name="--end")
    try:
        results = fetch_and_write_yahoo_daily_prices(
            symbols=_parse_symbols(symbols_value),
            start_date=start_date,
            end_date=end_date,
            output_root=output_root,
        )
    except PriceDataError as exc:
        raise typer.BadParameter(str(exc)) from exc

    for result in results:
        typer.echo(
            f"symbol={result.symbol} source_symbol={result.source_symbol} "
            f"row_count={result.row_count} observation_path={result.observation_path}"
        )
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        symbol_count=len(results),
        output_root=str(output_root),
    ).success("Fetched Yahoo daily price observations")


@prices_app.command("fetch-cboe", no_args_is_help=True)
def prices_fetch_cboe(
    symbols_value: str = typer.Argument(
        ...,
        metavar="SYMBOL[,SYMBOL...]",
        help="Comma-separated CBOE volatility index symbols to fetch.",
    ),
    start_date_value: str = typer.Option(
        ...,
        "--start",
        metavar="YYYY-MM-DD",
        help="First price date to fetch.",
    ),
    end_date_value: str = typer.Option(
        ...,
        "--end",
        metavar="YYYY-MM-DD",
        help="Last price date to fetch.",
    ),
    output_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--output-root",
        file_okay=False,
        help="Root directory for daily price observations.",
    ),
) -> None:
    """Fetch daily volatility index observations from CBOE historical CSVs."""

    start_date = _parse_date_option(start_date_value, option_name="--start")
    end_date = _parse_date_option(end_date_value, option_name="--end")
    try:
        results = fetch_and_write_cboe_index_daily_prices(
            symbols=_parse_symbols(symbols_value),
            start_date=start_date,
            end_date=end_date,
            output_root=output_root,
        )
    except PriceDataError as exc:
        raise typer.BadParameter(str(exc)) from exc

    for result in results:
        typer.echo(
            f"symbol={result.symbol} source_symbol={result.source_symbol} "
            f"row_count={result.row_count} observation_path={result.observation_path}"
        )
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        symbol_count=len(results),
        output_root=str(output_root),
    ).success("Fetched CBOE index price observations")


@prices_app.command("import-csv", no_args_is_help=True)
def prices_import_csv(
    symbol: str = typer.Argument(
        ...,
        help="Ticker symbol represented by the CSV.",
    ),
    csv_path: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local CSV with Date, Open, High, Low, Close, Volume columns.",
    ),
    output_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--output-root",
        file_okay=False,
        help="Root directory for daily price observations.",
    ),
    source: str = typer.Option(
        "csv",
        "--source",
        help="Source label to store with imported rows.",
    ),
    source_symbol: str | None = typer.Option(
        None,
        "--source-symbol",
        help="Symbol spelling used by the source CSV.",
    ),
) -> None:
    """Import daily OHLCV observations from a local CSV file."""

    try:
        result = import_daily_price_csv(
            symbol=symbol,
            csv_path=csv_path,
            output_root=output_root,
            source=source,
            source_symbol=source_symbol,
        )
    except PriceDataError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(
        f"symbol={result.symbol} source_symbol={result.source_symbol} "
        f"row_count={result.row_count} observation_path={result.observation_path}"
    )
    logger.bind(
        symbol=result.symbol,
        row_count=result.row_count,
        observation_path=str(result.observation_path),
    ).success("Imported daily price observations")


@market_series_app.command("fetch-fred", no_args_is_help=True)
def market_series_fetch_fred(
    series_ids_value: str = typer.Argument(
        ",".join(DEFAULT_FRED_MARKET_SERIES_IDS),
        metavar="SERIES[,SERIES...]",
        help="Comma-separated FRED series IDs to fetch.",
    ),
    start_date_value: str = typer.Option(
        ...,
        "--start",
        metavar="YYYY-MM-DD",
        help="First observation date to fetch.",
    ),
    end_date_value: str = typer.Option(
        ...,
        "--end",
        metavar="YYYY-MM-DD",
        help="Last observation date to fetch.",
    ),
    output_root: Path = typer.Option(
        DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
        "--output-root",
        file_okay=False,
        help="Root directory for scalar market series observations.",
    ),
) -> None:
    """Fetch scalar market series observations from FRED."""

    start_date = _parse_date_option(start_date_value, option_name="--start")
    end_date = _parse_date_option(end_date_value, option_name="--end")
    try:
        results = fetch_and_write_fred_series(
            series_ids=_parse_series_ids(series_ids_value),
            start_date=start_date,
            end_date=end_date,
            output_root=output_root,
        )
    except MarketSeriesError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _echo_market_series_fetch_results(results)
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        series_count=len(results),
        output_root=str(output_root),
    ).success("Fetched FRED market series observations")


@regime_app.command("snapshot", no_args_is_help=True)
def regime_snapshot(
    source_date_value: str = typer.Option(
        ...,
        "--date",
        metavar="YYYY-MM-DD",
        help="Market regime date to compute.",
    ),
    fetch_prices_flag: bool = typer.Option(
        False,
        "--fetch-prices",
        help="Refresh only daily prices for regime proxies before computing.",
    ),
    fetch_market_series_flag: bool = typer.Option(
        False,
        "--fetch-market-series",
        help="Refresh only FRED market series before computing.",
    ),
    refresh_sources_flag: bool = typer.Option(
        False,
        "--refresh-sources",
        help="Refresh all market regime sources: prices and FRED market series.",
    ),
    price_start_value: str | None = typer.Option(
        None,
        "--price-start",
        metavar="YYYY-MM-DD",
        help=(
            "First price date for --refresh-sources or --fetch-prices. "
            f"Defaults to {DEFAULT_DAILY_PRICE_LOOKBACK_DAYS} days before --date."
        ),
    ),
    price_end_value: str | None = typer.Option(
        None,
        "--price-end",
        metavar="YYYY-MM-DD",
        help="Last price date for --refresh-sources or --fetch-prices. Defaults to --date.",
    ),
    market_series_start_value: str | None = typer.Option(
        None,
        "--market-series-start",
        metavar="YYYY-MM-DD",
        help=(
            "First market series date for --refresh-sources or --fetch-market-series. "
            f"Defaults to {DEFAULT_DAILY_PRICE_LOOKBACK_DAYS} days before --date."
        ),
    ),
    market_series_end_value: str | None = typer.Option(
        None,
        "--market-series-end",
        metavar="YYYY-MM-DD",
        help=(
            "Last market series date for --refresh-sources or --fetch-market-series. "
            "Defaults to --date."
        ),
    ),
    price_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--price-root",
        file_okay=False,
        help="Root directory containing daily price observations.",
    ),
    market_series_root: Path = typer.Option(
        DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
        "--market-series-root",
        file_okay=False,
        help="Root directory containing scalar market series observations.",
    ),
    snapshot_root: Path = typer.Option(
        DEFAULT_REGIME_SNAPSHOT_ROOT,
        "--snapshot-root",
        file_okay=False,
        help="Root directory for market regime snapshots.",
    ),
    signal_snapshot_root: Path = typer.Option(
        DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
        "--signal-root",
        file_okay=False,
        help="Root directory for market signal snapshots.",
    ),
    signal_time: SignalTime = typer.Option(
        SignalTime.EOD,
        "--signal-time",
        help="Signal timing label. Regime date-level workflows currently support only eod.",
    ),
    show_detail: bool = typer.Option(
        False,
        "--detail/--no-detail",
        help=(
            "Print detailed regime evidence tables. "
            "Defaults to concise snapshot metadata; use regime report for recent trends."
        ),
    ),
) -> None:
    """Compute a market regime snapshot from market source observations."""

    source_date = _parse_source_date(source_date_value)
    refresh_prices = refresh_sources_flag or fetch_prices_flag
    refresh_market_series = refresh_sources_flag or fetch_market_series_flag
    if refresh_prices:
        price_start = (
            _parse_date_option(price_start_value, option_name="--price-start")
            if price_start_value
            else source_date - timedelta(days=DEFAULT_DAILY_PRICE_LOOKBACK_DAYS)
        )
        price_end = (
            _parse_date_option(price_end_value, option_name="--price-end")
            if price_end_value
            else source_date
        )
        try:
            price_refresh_result = refresh_regime_prices(
                start_date=price_start,
                end_date=price_end,
                price_root=price_root,
            )
        except RegimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _echo_regime_price_refresh_result(price_refresh_result)
        typer.echo("")

    if refresh_market_series:
        market_series_start = (
            _parse_date_option(market_series_start_value, option_name="--market-series-start")
            if market_series_start_value
            else source_date - timedelta(days=DEFAULT_DAILY_PRICE_LOOKBACK_DAYS)
        )
        market_series_end = (
            _parse_date_option(market_series_end_value, option_name="--market-series-end")
            if market_series_end_value
            else source_date
        )
        try:
            market_series_results = fetch_and_write_fred_series(
                series_ids=DEFAULT_FRED_MARKET_SERIES_IDS,
                start_date=market_series_start,
                end_date=market_series_end,
                output_root=market_series_root,
            )
        except MarketSeriesError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _echo_market_series_fetch_results(market_series_results)
        typer.echo("")

    try:
        result = compute_regime_snapshot(
            source_date=source_date,
            price_root=price_root,
            market_series_root=market_series_root,
            snapshot_root=snapshot_root,
            signal_snapshot_root=signal_snapshot_root,
            signal_time=signal_time,
            snapshot_version=None,
            write_snapshot=True,
            overwrite_snapshot=True,
            require_action_history=True,
        )
    except RegimeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _echo_regime_snapshot_result(result, show_detail=show_detail)


@regime_app.command("backfill", no_args_is_help=True)
def regime_backfill(
    start_date_value: str = typer.Option(
        ...,
        "--start",
        metavar="YYYY-MM-DD",
        help="First market regime date to compute.",
    ),
    end_date_value: str = typer.Option(
        ...,
        "--end",
        metavar="YYYY-MM-DD",
        help="Last market regime date to compute.",
    ),
    fetch_prices_flag: bool = typer.Option(
        False,
        "--fetch-prices",
        help="Refresh only daily prices for regime proxies before computing snapshots.",
    ),
    fetch_market_series_flag: bool = typer.Option(
        False,
        "--fetch-market-series",
        help="Refresh only FRED market series before computing snapshots.",
    ),
    refresh_sources_flag: bool = typer.Option(
        False,
        "--refresh-sources",
        help="Refresh all market regime sources: prices and FRED market series.",
    ),
    lookback_days: int = typer.Option(
        DEFAULT_DAILY_PRICE_LOOKBACK_DAYS,
        "--lookback-days",
        min=0,
        help="Warmup calendar days to fetch before --start when refreshing source data.",
    ),
    price_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--price-root",
        file_okay=False,
        help="Root directory containing daily price observations.",
    ),
    market_series_root: Path = typer.Option(
        DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
        "--market-series-root",
        file_okay=False,
        help="Root directory containing scalar market series observations.",
    ),
    snapshot_root: Path = typer.Option(
        DEFAULT_REGIME_SNAPSHOT_ROOT,
        "--snapshot-root",
        file_okay=False,
        help="Root directory for market regime snapshots.",
    ),
    signal_snapshot_root: Path = typer.Option(
        DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
        "--signal-root",
        file_okay=False,
        help="Root directory for market signal snapshots.",
    ),
    signal_time: SignalTime = typer.Option(
        SignalTime.EOD,
        "--signal-time",
        help="Signal timing label. Regime date-level workflows currently support only eod.",
    ),
    recompute_existing: bool = typer.Option(
        True,
        "--recompute-existing/--skip-existing",
        help=(
            "Recompute and overwrite existing same-version regime snapshots during backfill."
        ),
    ),
) -> None:
    """Backfill daily market regime and market signal snapshots."""

    start_date = _parse_date_option(start_date_value, option_name="--start")
    end_date = _parse_date_option(end_date_value, option_name="--end")
    fetch_start = start_date - timedelta(days=lookback_days)
    refresh_prices = refresh_sources_flag or fetch_prices_flag
    refresh_market_series = refresh_sources_flag or fetch_market_series_flag
    if refresh_prices:
        try:
            price_refresh_result = refresh_regime_prices(
                start_date=fetch_start,
                end_date=end_date,
                price_root=price_root,
            )
        except RegimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _echo_regime_price_refresh_result(price_refresh_result)
        typer.echo("")

    if refresh_market_series:
        try:
            market_series_results = fetch_and_write_fred_series(
                series_ids=DEFAULT_FRED_MARKET_SERIES_IDS,
                start_date=fetch_start,
                end_date=end_date,
                output_root=market_series_root,
            )
        except MarketSeriesError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _echo_market_series_fetch_results(market_series_results)
        typer.echo("")

    try:
        result = compute_regime_backfill(
            start_date=start_date,
            end_date=end_date,
            price_root=price_root,
            market_series_root=market_series_root,
            snapshot_root=snapshot_root,
            signal_snapshot_root=signal_snapshot_root,
            signal_time=signal_time,
            snapshot_version=None,
            write_snapshot=True,
            skip_existing=not recompute_existing,
            overwrite_snapshot=True,
        )
    except RegimeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _echo_regime_backfill_result(result)


@regime_app.command("outcomes", no_args_is_help=True)
def regime_outcomes(
    start_date_value: str = typer.Option(
        ...,
        "--start",
        metavar="YYYY-MM-DD",
        help="First market regime snapshot date to replay.",
    ),
    end_date_value: str = typer.Option(
        ...,
        "--end",
        metavar="YYYY-MM-DD",
        help="Last market regime snapshot date to replay.",
    ),
    snapshot_root: Path = typer.Option(
        DEFAULT_REGIME_SNAPSHOT_ROOT,
        "--snapshot-root",
        file_okay=False,
        help="Root directory containing market regime snapshots.",
    ),
    signal_snapshot_root: Path = typer.Option(
        DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
        "--signal-root",
        file_okay=False,
        help="Root directory containing market signal snapshots.",
    ),
    policy_snapshot_root: Path = typer.Option(
        DEFAULT_POLICY_SNAPSHOT_ROOT,
        "--policy-root",
        file_okay=False,
        help="Root directory containing portfolio policy snapshots.",
    ),
    price_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--price-root",
        file_okay=False,
        help="Root directory containing daily price observations.",
    ),
    horizons_value: str = typer.Option(
        DEFAULT_OUTCOME_HORIZONS_VALUE,
        "--horizons",
        help="Comma-separated forward trading-day horizons.",
    ),
    snapshot_version: str | None = typer.Option(
        None,
        "--snapshot-version",
        help="Snapshot version to replay. Defaults to current pillar version.",
    ),
    save_report: bool = typer.Option(
        False,
        "--save/--no-save",
        help="Write this outcome report to the standard versioned workbooks/outcomes-*.txt path.",
    ),
    outcome_group: RegimeOutcomeGroup = typer.Option(
        RegimeOutcomeGroup.ACTION,
        "--by",
        metavar="MODE",
        help=(
            "Outcome grouping to replay: regime, signal, action, posture, protect, redeploy, "
            "pressure, episode, or policy."
        ),
    ),
) -> None:
    """Replay forward SPY/QQQ outcomes for market-regime research buckets."""

    start_date = _parse_date_option(start_date_value, option_name="--start")
    end_date = _parse_date_option(end_date_value, option_name="--end")
    horizons = _parse_horizons(horizons_value)
    outcome_version = _outcome_artifact_version(
        outcome_group=outcome_group,
        snapshot_version=snapshot_version,
    )
    if outcome_group == RegimeOutcomeGroup.SIGNAL:
        try:
            signal_result = compute_market_signal_outcomes(
                start_date=start_date,
                end_date=end_date,
                signal_snapshot_root=signal_snapshot_root,
                price_root=price_root,
                horizons=horizons,
                snapshot_version=snapshot_version,
            )
        except RegimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _emit_regime_outcome_report(
            _market_signal_outcome_report_text(signal_result),
            save_report=save_report,
            outcome_group=outcome_group.value,
            artifact_version=outcome_version,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            snapshot_version=snapshot_version,
        )
        return
    if outcome_group == RegimeOutcomeGroup.ACTION:
        try:
            action_result = compute_regime_action_outcomes(
                start_date=start_date,
                end_date=end_date,
                snapshot_root=snapshot_root,
                signal_snapshot_root=signal_snapshot_root,
                price_root=price_root,
                horizons=horizons,
                snapshot_version=snapshot_version,
            )
        except RegimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _emit_regime_outcome_report(
            _regime_action_outcome_report_text(action_result),
            save_report=save_report,
            outcome_group=outcome_group.value,
            artifact_version=outcome_version,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            snapshot_version=snapshot_version,
        )
        return
    if outcome_group == RegimeOutcomeGroup.POSTURE:
        try:
            posture_result = compute_regime_posture_outcomes(
                start_date=start_date,
                end_date=end_date,
                snapshot_root=snapshot_root,
                price_root=price_root,
                horizons=horizons,
                snapshot_version=snapshot_version,
            )
        except RegimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _emit_regime_outcome_report(
            _regime_posture_outcome_report_text(posture_result),
            save_report=save_report,
            outcome_group=outcome_group.value,
            artifact_version=outcome_version,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            snapshot_version=snapshot_version,
        )
        return
    if outcome_group == RegimeOutcomeGroup.REDEPLOY:
        try:
            redeploy_result = compute_regime_redeploy_outcomes(
                start_date=start_date,
                end_date=end_date,
                snapshot_root=snapshot_root,
                price_root=price_root,
                horizons=horizons,
                snapshot_version=snapshot_version,
            )
        except RegimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _emit_regime_outcome_report(
            _regime_redeploy_outcome_report_text(redeploy_result),
            save_report=save_report,
            outcome_group=outcome_group.value,
            artifact_version=outcome_version,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            snapshot_version=snapshot_version,
        )
        return
    if outcome_group == RegimeOutcomeGroup.PROTECT:
        try:
            protect_result = compute_regime_protect_outcomes(
                start_date=start_date,
                end_date=end_date,
                snapshot_root=snapshot_root,
                price_root=price_root,
                horizons=horizons,
                snapshot_version=snapshot_version,
            )
            cluster_result = compute_regime_protect_clusters(
                start_date=start_date,
                end_date=end_date,
                snapshot_root=snapshot_root,
                price_root=price_root,
                horizons=horizons,
                snapshot_version=snapshot_version,
            )
        except RegimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _emit_regime_outcome_report(
            _regime_protect_outcome_report_text(protect_result, cluster_result),
            save_report=save_report,
            outcome_group=outcome_group.value,
            artifact_version=outcome_version,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            snapshot_version=snapshot_version,
        )
        return
    if outcome_group == RegimeOutcomeGroup.PRESSURE:
        try:
            pressure_result = compute_regime_pressure_outcomes(
                start_date=start_date,
                end_date=end_date,
                snapshot_root=snapshot_root,
                signal_snapshot_root=signal_snapshot_root,
                price_root=price_root,
                horizons=horizons,
                snapshot_version=snapshot_version,
            )
        except RegimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _emit_regime_outcome_report(
            _regime_pressure_outcome_report_text(pressure_result),
            save_report=save_report,
            outcome_group=outcome_group.value,
            artifact_version=outcome_version,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            snapshot_version=snapshot_version,
        )
        return
    if outcome_group == RegimeOutcomeGroup.EPISODE:
        try:
            episode_result = compute_regime_correction_episodes(
                start_date=start_date,
                end_date=end_date,
                snapshot_root=snapshot_root,
                price_root=price_root,
                snapshot_version=snapshot_version,
            )
        except RegimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _emit_regime_outcome_report(
            _regime_correction_episode_report_text(episode_result),
            save_report=save_report,
            outcome_group=outcome_group.value,
            artifact_version=outcome_version,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            snapshot_version=snapshot_version,
        )
        return
    if outcome_group == RegimeOutcomeGroup.POLICY:
        try:
            policy_result = compute_portfolio_policy_outcomes(
                start_date=start_date,
                end_date=end_date,
                policy_snapshot_root=policy_snapshot_root,
                price_root=price_root,
                horizons=horizons,
                snapshot_version=snapshot_version,
            )
        except PortfolioPolicyError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _emit_regime_outcome_report(
            _policy_outcome_report_text(policy_result),
            save_report=save_report,
            outcome_group=outcome_group.value,
            artifact_version=outcome_version,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            snapshot_version=snapshot_version,
        )
        return
    try:
        result = compute_regime_outcomes(
            start_date=start_date,
            end_date=end_date,
            snapshot_root=snapshot_root,
            price_root=price_root,
            horizons=horizons,
            snapshot_version=snapshot_version,
        )
    except RegimeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _emit_regime_outcome_report(
        _regime_outcome_report_text(result),
        save_report=save_report,
        outcome_group=outcome_group.value,
        artifact_version=outcome_version,
        start_date=start_date,
        end_date=end_date,
        horizons=horizons,
        snapshot_version=snapshot_version,
    )


@store_app.command("refresh")
def store_refresh(
    db_path: Path = typer.Option(
        DEFAULT_RESEARCH_DB_PATH,
        "--db",
        dir_okay=False,
        help="DuckDB file to rebuild from local observations and snapshots.",
    ),
    price_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--price-root",
        file_okay=False,
        help="Root directory containing daily price observations.",
    ),
    market_series_root: Path = typer.Option(
        DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
        "--market-series-root",
        file_okay=False,
        help="Root directory containing scalar market series observations.",
    ),
    regime_snapshot_root: Path = typer.Option(
        DEFAULT_REGIME_SNAPSHOT_ROOT,
        "--regime-root",
        file_okay=False,
        help="Root directory containing market regime snapshots.",
    ),
    market_signal_snapshot_root: Path = typer.Option(
        DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
        "--signal-root",
        file_okay=False,
        help="Root directory containing market signal snapshots.",
    ),
    candidate_snapshot_root: Path = typer.Option(
        DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
        "--candidate-root",
        file_okay=False,
        help="Root directory containing Bulltard candidate snapshots.",
    ),
    policy_snapshot_root: Path = typer.Option(
        DEFAULT_POLICY_SNAPSHOT_ROOT,
        "--policy-root",
        file_okay=False,
        help="Root directory containing portfolio policy snapshots.",
    ),
    bulltard_observation_root: Path = typer.Option(
        DEFAULT_OBSERVATIONS_ROOT,
        "--bulltard-root",
        file_okay=False,
        help="Root directory containing Bulltard source observations.",
    ),
    parquet_root: Path | None = typer.Option(
        None,
        "--parquet-root",
        file_okay=False,
        help="Optional directory for Parquet exports of each rebuilt table.",
    ),
) -> None:
    """Refresh the local DuckDB research store from saved files."""

    try:
        result = refresh_research_store(
            db_path=db_path,
            price_root=price_root,
            market_series_root=market_series_root,
            regime_snapshot_root=regime_snapshot_root,
            market_signal_snapshot_root=market_signal_snapshot_root,
            candidate_snapshot_root=candidate_snapshot_root,
            policy_snapshot_root=policy_snapshot_root,
            bulltard_observation_root=bulltard_observation_root,
            parquet_root=parquet_root,
        )
    except ResearchStoreError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _echo_store_refresh_result(result)


@store_app.command("tables")
def store_tables(
    db_path: Path = typer.Option(
        DEFAULT_RESEARCH_DB_PATH,
        "--db",
        exists=True,
        dir_okay=False,
        readable=True,
        help="DuckDB file to inspect.",
    ),
) -> None:
    """Show row counts for local research store tables."""

    try:
        result = summarize_research_store(db_path=db_path)
    except ResearchStoreError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(format_query_result(result))


@store_app.command("query", no_args_is_help=True)
def store_query(
    sql: str = typer.Argument(
        ...,
        help="SQL query to run against the local DuckDB research store.",
    ),
    db_path: Path = typer.Option(
        DEFAULT_RESEARCH_DB_PATH,
        "--db",
        exists=True,
        dir_okay=False,
        readable=True,
        help="DuckDB file to query.",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        min=1,
        help="Maximum rows to print.",
    ),
) -> None:
    """Run a read-only SQL query against the local research store."""

    try:
        result = query_research_store(query=sql, db_path=db_path)
    except ResearchStoreError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(format_query_result(result, limit=limit))


@regime_app.command("policy", no_args_is_help=True)
def policy_snapshot(
    source_date_value: str = typer.Option(
        ...,
        "--date",
        metavar="YYYY-MM-DD",
        help="Portfolio policy date to compute.",
    ),
    regime_snapshot_root: Path = typer.Option(
        DEFAULT_REGIME_SNAPSHOT_ROOT,
        "--regime-root",
        file_okay=False,
        help="Root directory containing market regime snapshots.",
    ),
    market_signal_snapshot_root: Path = typer.Option(
        DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
        "--signal-root",
        file_okay=False,
        help="Root directory containing market signal snapshots.",
    ),
    candidate_snapshot_root: Path = typer.Option(
        DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
        "--candidate-root",
        file_okay=False,
        help="Root directory containing Bulltard candidate snapshots.",
    ),
    policy_snapshot_root: Path = typer.Option(
        DEFAULT_POLICY_SNAPSHOT_ROOT,
        "--policy-root",
        file_okay=False,
        help="Root directory for portfolio policy snapshots.",
    ),
    signal_time: SignalTime = typer.Option(
        SignalTime.EOD,
        "--signal-time",
        help="Signal timing label for upstream regime snapshots.",
    ),
    snapshot_version: str | None = typer.Option(
        None,
        "--snapshot-version",
        help="Snapshot version. Defaults to current pillar version.",
    ),
    write_snapshot: bool = typer.Option(
        True,
        "--write/--no-write",
        help="Write the portfolio policy snapshot.",
    ),
    show_detail: bool = typer.Option(
        False,
        "--detail/--no-detail",
        help=(
            "Print the policy posture table. "
            "Defaults to concise snapshot metadata."
        ),
    ),
) -> None:
    """Compute a portfolio policy snapshot."""

    source_date = _parse_source_date(source_date_value)
    try:
        result = compute_portfolio_policy_snapshot(
            source_date=source_date,
            regime_snapshot_root=regime_snapshot_root,
            market_signal_snapshot_root=market_signal_snapshot_root,
            candidate_snapshot_root=candidate_snapshot_root,
            policy_snapshot_root=policy_snapshot_root,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
            write_snapshot=write_snapshot,
        )
    except PortfolioPolicyError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _echo_policy_snapshot_result(result, show_detail=show_detail)


@regime_app.command("policy-backfill", no_args_is_help=True)
def policy_backfill(
    start_date_value: str = typer.Option(
        ...,
        "--start",
        metavar="YYYY-MM-DD",
        help="First policy snapshot date to compute.",
    ),
    end_date_value: str = typer.Option(
        ...,
        "--end",
        metavar="YYYY-MM-DD",
        help="Last policy snapshot date to compute.",
    ),
    regime_snapshot_root: Path = typer.Option(
        DEFAULT_REGIME_SNAPSHOT_ROOT,
        "--regime-root",
        file_okay=False,
        help="Root directory containing market regime snapshots.",
    ),
    market_signal_snapshot_root: Path = typer.Option(
        DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
        "--signal-root",
        file_okay=False,
        help="Root directory containing market signal snapshots.",
    ),
    candidate_snapshot_root: Path = typer.Option(
        DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
        "--candidate-root",
        file_okay=False,
        help="Root directory containing Bulltard candidate snapshots.",
    ),
    policy_snapshot_root: Path = typer.Option(
        DEFAULT_POLICY_SNAPSHOT_ROOT,
        "--policy-root",
        file_okay=False,
        help="Root directory for portfolio policy snapshots.",
    ),
    signal_time: SignalTime = typer.Option(
        SignalTime.EOD,
        "--signal-time",
        help="Signal timing label for upstream regime snapshots.",
    ),
    snapshot_version: str | None = typer.Option(
        None,
        "--snapshot-version",
        help=(
            "Snapshot version. Defaults to current pillar version for each date."
        ),
    ),
    write_snapshot: bool = typer.Option(
        True,
        "--write/--no-write",
        help="Write portfolio policy snapshots.",
    ),
) -> None:
    """Backfill portfolio policy snapshots from saved regime snapshots."""

    start_date = _parse_date_option(start_date_value, option_name="--start")
    end_date = _parse_date_option(end_date_value, option_name="--end")
    try:
        result = compute_portfolio_policy_backfill(
            start_date=start_date,
            end_date=end_date,
            regime_snapshot_root=regime_snapshot_root,
            market_signal_snapshot_root=market_signal_snapshot_root,
            candidate_snapshot_root=candidate_snapshot_root,
            policy_snapshot_root=policy_snapshot_root,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
            write_snapshot=write_snapshot,
        )
    except PortfolioPolicyError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _echo_policy_backfill_result(result)


@regime_app.command("report", no_args_is_help=True)
def report_daily(
    source_date_value: str = typer.Option(
        ...,
        "--date",
        metavar="YYYY-MM-DD",
        help="Last regime snapshot date to include.",
    ),
    lookback_days: int = typer.Option(
        10,
        "--days",
        min=1,
        help="Number of saved trading-day regime snapshots to include.",
    ),
    regime_snapshot_root: Path = typer.Option(
        DEFAULT_REGIME_SNAPSHOT_ROOT,
        "--regime-root",
        file_okay=False,
        help="Root directory containing market regime snapshots.",
    ),
    signal_time: SignalTime = typer.Option(
        SignalTime.EOD,
        "--signal-time",
        help="Signal timing label for upstream regime snapshots.",
    ),
    snapshot_version: str | None = typer.Option(
        None,
        "--snapshot-version",
        help="Snapshot version. Defaults to current pillar version.",
    ),
) -> None:
    """Render recent market-regime trend tables."""

    source_date = _parse_source_date(source_date_value)
    try:
        result = compute_regime_recent_report(
            source_date=source_date,
            lookback_days=lookback_days,
            snapshot_root=regime_snapshot_root,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
        )
    except RegimeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _echo_regime_recent_report_result(result)


@regime_app.command("export", no_args_is_help=True)
def regime_export(
    start_date_value: str = typer.Option(
        ...,
        "--start",
        metavar="YYYY-MM-DD",
        help="First saved regime snapshot date to export.",
    ),
    end_date_value: str = typer.Option(
        ...,
        "--end",
        metavar="YYYY-MM-DD",
        help="Last saved regime snapshot date to export.",
    ),
    snapshot_root: Path = typer.Option(
        DEFAULT_REGIME_SNAPSHOT_ROOT,
        "--snapshot-root",
        file_okay=False,
        help="Root directory containing market regime snapshots.",
    ),
    price_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--price-root",
        file_okay=False,
        help="Root directory containing daily price observations.",
    ),
    signal_time: SignalTime = typer.Option(
        SignalTime.EOD,
        "--signal-time",
        help="Signal timing label for snapshots to export.",
    ),
    snapshot_version: str | None = typer.Option(
        None,
        "--snapshot-version",
        help="Snapshot version to export. Defaults to current pillar version.",
    ),
) -> None:
    """Export saved regime snapshots to standard XLSX and CSV files."""

    start_date = _parse_date_option(start_date_value, option_name="--start")
    end_date = _parse_date_option(end_date_value, option_name="--end")
    try:
        workbook_path, csv_path = regime_export_paths(
            version=snapshot_version or REGIME_SNAPSHOT_VERSION
        )
        result = export_regime_workbook(
            start_date=start_date,
            end_date=end_date,
            workbook_path=workbook_path,
            csv_path=csv_path,
            snapshot_root=snapshot_root,
            price_root=price_root,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
        )
    except RegimeExportError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _echo_regime_export_result(result)


@bulltard_app.command("inspect-recap", no_args_is_help=True)
def inspect_recap(
    recap_path: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local recap text or HTML file.",
    ),
    show_secret_url: bool = typer.Option(
        False,
        "--show-secret-url",
        help="Print the full temporary signed URL instead of a redacted copy.",
    ),
) -> None:
    """Extract the signed Bulltard source URL from a local recap."""

    try:
        logger.bind(path=str(recap_path)).info("Reading Bulltard recap")
        signed_url = extract_signed_source_url(recap_path.read_text(encoding="utf-8"))
    except SignedSourceUrlError as exc:
        raise typer.BadParameter(str(exc), param_hint="recap_path") from exc

    output_url = signed_url if show_secret_url else redact_capability_url(signed_url)
    typer.echo(output_url)
    logger.bind(path=str(recap_path), url=redact_capability_url(signed_url)).success(
        "Inspected Bulltard recap"
    )


@bulltard_app.command("ingest", no_args_is_help=True)
def ingest(
    recap_path: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local recap text or HTML file containing the signed Bulltard link.",
    ),
    source_date_value: str = typer.Option(
        ...,
        "--date",
        metavar="YYYY-MM-DD",
        help="Source date represented by the recap.",
    ),
    view: BulltardView = typer.Option(
        BulltardView.RANKED_OPTION_TRADES,
        "--view",
        help="Bulltard view to ingest.",
    ),
    output_root: Path = typer.Option(
        DEFAULT_OBSERVATIONS_ROOT,
        "--output-root",
        file_okay=False,
        help="Root directory for structured Bulltard observations.",
    ),
    debug_root: Path = typer.Option(
        DEFAULT_DEBUG_ROOT,
        "--debug-root",
        file_okay=False,
        help="Root directory for temporary Bulltard parser debug payloads.",
    ),
) -> None:
    """Retrieve and parse one targeted Bulltard view."""

    source_date = _parse_source_date(source_date_value)

    try:
        plan = build_ingest_plan(
            source_date=source_date,
            view=view,
            recap_path=recap_path,
            output_root=output_root,
        )
        result = ingest_planned_view(plan, debug_root=debug_root)
    except IngestError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"view={plan.view.value}")
    typer.echo(f"route_path={plan.view.route_path}")
    typer.echo(f"signed_url={redact_capability_url(plan.signed_url)}")
    typer.echo(f"final_url={redact_capability_url(result.fetched_view.final_url)}")
    typer.echo(f"status_code={result.fetched_view.status_code}")
    typer.echo(f"byte_count={result.fetched_view.byte_count}")
    typer.echo(f"debug_path={result.fetched_view.debug_path}")
    typer.echo(f"observation_path={result.observation_path}")
    typer.echo(f"row_count={result.row_count}")
    logger.bind(
        source_date=source_date.isoformat(),
        view=plan.view.value,
        debug_path=str(result.fetched_view.debug_path),
        observation_path=str(result.observation_path),
        row_count=result.row_count,
    ).success("Completed Bulltard ingest")


@bulltard_app.command("ticker", no_args_is_help=True)
def ticker(
    symbol: str = typer.Argument(
        ...,
        help="Ticker symbol to retrieve from Bulltard.",
    ),
    recap_path: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local recap text or HTML file containing the signed Bulltard link.",
    ),
    source_date_value: str = typer.Option(
        ...,
        "--date",
        metavar="YYYY-MM-DD",
        help="Source date represented by the recap.",
    ),
    debug_root: Path = typer.Option(
        DEFAULT_DEBUG_ROOT,
        "--debug-root",
        file_okay=False,
        help="Root directory for temporary Bulltard parser debug payloads.",
    ),
    output_root: Path = typer.Option(
        DEFAULT_OBSERVATIONS_ROOT,
        "--output-root",
        file_okay=False,
        help="Root directory for structured Bulltard observations.",
    ),
) -> None:
    """Retrieve and parse one Bulltard ticker detail page."""

    source_date = _parse_source_date(source_date_value)
    try:
        result = ingest_ticker_page(
            source_date=source_date,
            symbol=symbol,
            recap_path=recap_path,
            output_root=output_root,
            debug_root=debug_root,
        )
    except IngestError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"symbol={result.fetched_page.symbol}")
    typer.echo(f"signed_url={redact_capability_url(result.fetched_page.signed_url)}")
    typer.echo(f"final_url={redact_capability_url(result.fetched_page.final_url)}")
    typer.echo(f"status_code={result.fetched_page.status_code}")
    typer.echo(f"byte_count={result.fetched_page.byte_count}")
    typer.echo(f"debug_path={result.fetched_page.debug_path}")
    typer.echo(f"observation_path={result.observation_path}")
    typer.echo(f"row_count={result.row_count}")
    logger.bind(
        source_date=source_date.isoformat(),
        symbol=result.fetched_page.symbol,
        debug_path=str(result.fetched_page.debug_path),
        observation_path=str(result.observation_path),
        row_count=result.row_count,
    ).success("Completed Bulltard ticker ingest")


@bulltard_app.command("candidates", no_args_is_help=True)
def candidates(
    source_date_value: str = typer.Option(
        ...,
        "--date",
        metavar="YYYY-MM-DD",
        help="Source date to review.",
    ),
    observations_root: Path = typer.Option(
        DEFAULT_OBSERVATIONS_ROOT,
        "--observations-root",
        file_okay=False,
        help="Root directory containing structured Bulltard observations.",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        min=1,
        help="Maximum number of ranked candidates to show.",
    ),
) -> None:
    """Review Bulltard ranked candidates with available ticker flow."""

    source_date = _parse_source_date(source_date_value)
    try:
        reviews = load_candidate_reviews(
            source_date=source_date,
            observations_root=observations_root,
            limit=limit,
        )
    except CandidateReviewError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(format_candidate_reviews(reviews))
    missing_detail_count = sum(1 for review in reviews if review.detail_rows == 0)
    logger.bind(
        source_date=source_date.isoformat(),
        candidate_count=len(reviews),
        missing_detail_count=missing_detail_count,
    ).success("Reviewed Bulltard candidates")


@bulltard_app.command("validate", no_args_is_help=True)
def validate_candidates(
    source_date_value: str = typer.Option(
        ...,
        "--date",
        metavar="YYYY-MM-DD",
        help="Source date to validate.",
    ),
    observations_root: Path = typer.Option(
        DEFAULT_OBSERVATIONS_ROOT,
        "--observations-root",
        file_okay=False,
        help="Root directory containing structured Bulltard observations.",
    ),
    price_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--price-root",
        file_okay=False,
        help="Root directory containing daily price observations.",
    ),
    snapshot_root: Path = typer.Option(
        DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
        "--snapshot-root",
        file_okay=False,
        help="Root directory for Bulltard candidate validation snapshots.",
    ),
    limit: int = typer.Option(
        12,
        "--limit",
        min=1,
        help="Maximum number of candidates to validate.",
    ),
    min_dollar_volume: float = typer.Option(
        DEFAULT_MIN_DOLLAR_VOLUME,
        "--min-dollar-volume",
        min=0.0,
        help="Minimum daily dollar volume for the basic liquidity gate.",
    ),
    signal_time: SignalTime = typer.Option(
        SignalTime.EOD,
        "--signal-time",
        help="Signal timing label for candidate validation snapshots.",
    ),
    snapshot_version: str | None = typer.Option(
        None,
        "--snapshot-version",
        help="Snapshot version. Defaults to current pillar version.",
    ),
    write_snapshot: bool = typer.Option(
        True,
        "--write/--no-write",
        help="Write point-in-time candidate validation snapshots.",
    ),
) -> None:
    """Validate Bulltard candidates against independent price observations."""

    source_date = _parse_source_date(source_date_value)
    try:
        result = validate_bulltard_candidates(
            source_date=source_date,
            observations_root=observations_root,
            price_root=price_root,
            snapshot_root=snapshot_root,
            limit=limit,
            min_dollar_volume=min_dollar_volume,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
            write_snapshot=write_snapshot,
        )
    except CandidateValidationError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if result.snapshot_path is not None:
        typer.echo(f"snapshot_path={result.snapshot_path}")
    typer.echo(f"candidate_count={len(result.snapshots)}")
    typer.echo(_format_validation_summary(result.summary))
    typer.echo("")
    typer.echo(result.table)


@bulltard_app.command("refresh-prices", no_args_is_help=True)
def refresh_prices(
    source_date_value: str = typer.Option(
        ...,
        "--date",
        metavar="YYYY-MM-DD",
        help="Source date whose captured candidates should drive the price refresh.",
    ),
    start_date_value: str = typer.Option(
        ...,
        "--start",
        metavar="YYYY-MM-DD",
        help="First price date to fetch.",
    ),
    end_date_value: str | None = typer.Option(
        None,
        "--end",
        metavar="YYYY-MM-DD",
        help="Last price date to fetch. Defaults to today.",
    ),
    observations_root: Path = typer.Option(
        DEFAULT_OBSERVATIONS_ROOT,
        "--observations-root",
        file_okay=False,
        help="Root directory containing structured Bulltard observations.",
    ),
    price_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--price-root",
        file_okay=False,
        help="Root directory for daily price observations.",
    ),
    limit: int = typer.Option(
        12,
        "--limit",
        min=1,
        help="Maximum number of candidates whose prices should be refreshed.",
    ),
) -> None:
    """Refresh Yahoo prices for captured Bulltard candidates and benchmarks."""

    source_date = _parse_source_date(source_date_value)
    start_date = _parse_date_option(start_date_value, option_name="--start")
    end_date = (
        _parse_date_option(end_date_value, option_name="--end") if end_date_value else date.today()
    )
    try:
        result = refresh_candidate_price_set(
            source_date=source_date,
            start_date=start_date,
            end_date=end_date,
            observations_root=observations_root,
            price_root=price_root,
            limit=limit,
        )
    except DailyWorkflowError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _echo_price_refresh_result(result)


@bulltard_app.command("outcomes", no_args_is_help=True)
def outcomes(
    start_date_value: str = typer.Option(
        ...,
        "--start",
        metavar="YYYY-MM-DD",
        help="First candidate snapshot date to replay.",
    ),
    end_date_value: str = typer.Option(
        ...,
        "--end",
        metavar="YYYY-MM-DD",
        help="Last candidate snapshot date to replay.",
    ),
    snapshot_root: Path = typer.Option(
        DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
        "--snapshot-root",
        file_okay=False,
        help="Root directory containing Bulltard candidate validation snapshots.",
    ),
    price_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--price-root",
        file_okay=False,
        help="Root directory containing daily price observations.",
    ),
    observations_root: Path = typer.Option(
        DEFAULT_OBSERVATIONS_ROOT,
        "--observations-root",
        file_okay=False,
        help="Root directory containing structured Bulltard observations for flow cohorts.",
    ),
    regime_snapshot_root: Path = typer.Option(
        DEFAULT_REGIME_SNAPSHOT_ROOT,
        "--regime-root",
        file_okay=False,
        help="Root directory containing market regime snapshots for regime cohorts.",
    ),
    horizons_value: str = typer.Option(
        DEFAULT_OUTCOME_HORIZONS_VALUE,
        "--horizons",
        help="Comma-separated forward trading-day horizons.",
    ),
) -> None:
    """Replay forward outcomes for saved Bulltard candidate snapshots."""

    start_date = _parse_date_option(start_date_value, option_name="--start")
    end_date = _parse_date_option(end_date_value, option_name="--end")
    try:
        result = compute_bulltard_outcomes(
            start_date=start_date,
            end_date=end_date,
            snapshot_root=snapshot_root,
            price_root=price_root,
            observations_root=observations_root,
            regime_snapshot_root=regime_snapshot_root,
            horizons=_parse_horizons(horizons_value),
        )
    except CandidateOutcomeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"outcome_count={len(result.outcomes)}")
    typer.echo(f"available_outcome_count={_available_candidate_outcome_count(result)}")
    typer.echo("")
    typer.echo(result.table)


@bulltard_app.command("trades-of-interest", no_args_is_help=True)
def trades_of_interest(
    recap_path: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local recap text or HTML file.",
    ),
    source_date_value: str = typer.Option(
        ...,
        "--date",
        metavar="YYYY-MM-DD",
        help="Source date represented by the recap.",
    ),
    output_root: Path = typer.Option(
        DEFAULT_OBSERVATIONS_ROOT,
        "--output-root",
        file_okay=False,
        help="Root directory for structured Bulltard observations.",
    ),
) -> None:
    """Parse recap Trades Of Interest into observations."""

    source_date = _parse_source_date(source_date_value)
    try:
        result = ingest_trades_of_interest(
            source_date=source_date,
            recap_path=recap_path,
            output_root=output_root,
        )
    except IngestError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"observation_path={result.observation_path}")
    typer.echo(f"row_count={result.row_count}")
    typer.echo(f"symbols={','.join(result.symbols)}")
    logger.bind(
        source_date=source_date.isoformat(),
        row_count=result.row_count,
        symbols=result.symbols,
        observation_path=str(result.observation_path),
    ).success("Completed Bulltard Trades Of Interest ingest")


@bulltard_app.command("daily", no_args_is_help=True)
def daily(
    recap_path: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local recap text or HTML file containing the signed Bulltard link.",
    ),
    source_date_value: str = typer.Option(
        ...,
        "--date",
        metavar="YYYY-MM-DD",
        help="Source date represented by the recap.",
    ),
    output_root: Path = typer.Option(
        DEFAULT_OBSERVATIONS_ROOT,
        "--output-root",
        file_okay=False,
        help="Root directory for structured Bulltard observations.",
    ),
    debug_root: Path = typer.Option(
        DEFAULT_DEBUG_ROOT,
        "--debug-root",
        file_okay=False,
        help="Root directory for temporary Bulltard parser debug payloads.",
    ),
    fetch_ticker_details: bool = typer.Option(
        True,
        "--ticker-details/--no-ticker-details",
        help="Fetch ticker detail pages for selected candidates.",
    ),
    top_ranked: int = typer.Option(
        0,
        "--top-ranked",
        min=0,
        help="Also fetch ticker details for the top N ranked database names.",
    ),
    extra_tickers_value: str = typer.Option(
        "",
        "--ticker",
        help="Comma-separated extra ticker symbols to fetch details for.",
    ),
    limit: int = typer.Option(
        12,
        "--limit",
        min=1,
        help="Maximum number of candidates to show in the review table.",
    ),
    validate_candidates_flag: bool = typer.Option(
        False,
        "--validate",
        help="Also validate candidates against local daily price observations.",
    ),
    fetch_prices_flag: bool = typer.Option(
        False,
        "--fetch-prices",
        help="Also refresh Yahoo daily prices for candidates and SPY/QQQ.",
    ),
    price_start_value: str | None = typer.Option(
        None,
        "--price-start",
        metavar="YYYY-MM-DD",
        help=(
            "First price date for --fetch-prices. "
            f"Defaults to {DEFAULT_DAILY_PRICE_LOOKBACK_DAYS} days before --date."
        ),
    ),
    price_end_value: str | None = typer.Option(
        None,
        "--price-end",
        metavar="YYYY-MM-DD",
        help="Last price date for --fetch-prices. Defaults to --date.",
    ),
    price_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--price-root",
        file_okay=False,
        help="Root directory containing daily price observations.",
    ),
    snapshot_root: Path = typer.Option(
        DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
        "--snapshot-root",
        file_okay=False,
        help="Root directory for Bulltard candidate validation snapshots.",
    ),
    min_dollar_volume: float = typer.Option(
        DEFAULT_MIN_DOLLAR_VOLUME,
        "--min-dollar-volume",
        min=0.0,
        help="Minimum daily dollar volume for the basic liquidity gate.",
    ),
    signal_time: SignalTime = typer.Option(
        SignalTime.EOD,
        "--signal-time",
        help="Signal timing label for candidate validation snapshots.",
    ),
    snapshot_version: str | None = typer.Option(
        None,
        "--snapshot-version",
        help="Candidate validation snapshot version. Defaults to current pillar version.",
    ),
    compute_outcomes_flag: bool = typer.Option(
        False,
        "--outcomes",
        help="Also replay forward outcomes from saved validation snapshots.",
    ),
    outcome_start_value: str | None = typer.Option(
        None,
        "--outcome-start",
        metavar="YYYY-MM-DD",
        help=(
            "First candidate snapshot date to replay for --outcomes. "
            "Defaults to the earliest saved snapshot date, or --date when none exists."
        ),
    ),
    outcome_end_value: str | None = typer.Option(
        None,
        "--outcome-end",
        metavar="YYYY-MM-DD",
        help="Last candidate snapshot date to replay for --outcomes. Defaults to --date.",
    ),
    horizons_value: str = typer.Option(
        DEFAULT_OUTCOME_HORIZONS_VALUE,
        "--horizons",
        help="Comma-separated forward trading-day horizons for --outcomes.",
    ),
) -> None:
    """Run the daily Bulltard candidate workflow."""

    source_date = _parse_source_date(source_date_value)
    try:
        result = run_daily_workflow(
            source_date=source_date,
            recap_path=recap_path,
            output_root=output_root,
            debug_root=debug_root,
            fetch_ticker_details=fetch_ticker_details,
            top_ranked=top_ranked,
            extra_tickers=_parse_extra_tickers(extra_tickers_value),
            limit=limit,
        )
    except DailyWorkflowError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"ranked_observation_path={result.ranked_result.observation_path}")
    typer.echo(f"ranked_row_count={result.ranked_result.row_count}")
    if result.trades_of_interest_result is None:
        typer.echo("trades_of_interest_row_count=0")
        typer.echo("trades_of_interest_symbols=")
    else:
        typer.echo(f"trades_of_interest_path={result.trades_of_interest_result.observation_path}")
        typer.echo(f"trades_of_interest_row_count={result.trades_of_interest_result.row_count}")
        typer.echo(
            f"trades_of_interest_symbols={','.join(result.trades_of_interest_result.symbols)}"
        )
    typer.echo(
        "ticker_detail_symbols="
        + ",".join(ticker_result.fetched_page.symbol for ticker_result in result.ticker_results)
    )
    if result.ticker_failures:
        typer.echo(
            "ticker_detail_failures="
            + ",".join(f"{failure.symbol}:{failure.error}" for failure in result.ticker_failures)
        )
    typer.echo("")
    typer.echo(result.candidate_table)

    if fetch_prices_flag:
        price_start = (
            _parse_date_option(price_start_value, option_name="--price-start")
            if price_start_value
            else source_date - timedelta(days=DEFAULT_DAILY_PRICE_LOOKBACK_DAYS)
        )
        price_end = (
            _parse_date_option(price_end_value, option_name="--price-end")
            if price_end_value
            else source_date
        )
        try:
            price_refresh_result = refresh_candidate_price_set(
                source_date=source_date,
                start_date=price_start,
                end_date=price_end,
                observations_root=output_root,
                price_root=price_root,
                limit=limit,
            )
        except DailyWorkflowError as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo("")
        _echo_price_refresh_result(price_refresh_result)

    if validate_candidates_flag:
        try:
            validation_result = validate_bulltard_candidates(
                source_date=source_date,
                observations_root=output_root,
                price_root=price_root,
                snapshot_root=snapshot_root,
                limit=limit,
                min_dollar_volume=min_dollar_volume,
                signal_time=signal_time,
                snapshot_version=snapshot_version,
                write_snapshot=True,
            )
        except CandidateValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo("")
        typer.echo(f"candidate_validation_snapshot_path={validation_result.snapshot_path}")
        typer.echo(f"candidate_validation_count={len(validation_result.snapshots)}")
        typer.echo(
            _format_validation_summary(
                validation_result.summary,
                prefix="candidate_validation_summary",
            )
        )
        typer.echo("")
        typer.echo(validation_result.table)

    if compute_outcomes_flag:
        outcome_start = (
            _parse_date_option(outcome_start_value, option_name="--outcome-start")
            if outcome_start_value
            else _default_outcome_start(snapshot_root=snapshot_root, fallback=source_date)
        )
        outcome_end = (
            _parse_date_option(outcome_end_value, option_name="--outcome-end")
            if outcome_end_value
            else source_date
        )
        try:
            outcome_result = compute_bulltard_outcomes(
                start_date=outcome_start,
                end_date=outcome_end,
                snapshot_root=snapshot_root,
                price_root=price_root,
                observations_root=output_root,
                regime_snapshot_root=None,
                horizons=_parse_horizons(horizons_value),
            )
        except CandidateOutcomeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo("")
        typer.echo(f"outcome_count={len(outcome_result.outcomes)}")
        typer.echo(f"available_outcome_count={_available_candidate_outcome_count(outcome_result)}")
        typer.echo("")
        typer.echo(outcome_result.table)


def _parse_source_date(value: str) -> date:
    return _parse_date_option(value, option_name="--date")


def _parse_date_option(value: str, *, option_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(
            "Date must use YYYY-MM-DD format",
            param_hint=option_name,
        ) from exc


def _parse_symbols(value: str) -> tuple[str, ...]:
    symbols = tuple(symbol.strip() for symbol in value.split(",") if symbol.strip())
    if not symbols:
        raise typer.BadParameter("At least one symbol is required")
    return symbols


def _parse_series_ids(value: str) -> tuple[str, ...]:
    series_ids = tuple(series_id.strip() for series_id in value.split(",") if series_id.strip())
    if not series_ids:
        raise typer.BadParameter("At least one series ID is required")
    return series_ids


def _parse_horizons(value: str) -> tuple[int, ...]:
    raw_horizons = tuple(part.strip() for part in value.split(",") if part.strip())
    if not raw_horizons:
        raise typer.BadParameter("At least one horizon is required", param_hint="--horizons")
    try:
        horizons = tuple(int(raw_horizon) for raw_horizon in raw_horizons)
    except ValueError as exc:
        raise typer.BadParameter(
            "Horizons must be comma-separated integers",
            param_hint="--horizons",
        ) from exc
    if any(horizon <= 0 for horizon in horizons):
        raise typer.BadParameter("Horizons must be positive", param_hint="--horizons")
    return horizons


def _parse_extra_tickers(value: str) -> tuple[str, ...]:
    return tuple(symbol.strip() for symbol in value.split(",") if symbol.strip())


def _default_recap_path(source_date: date) -> Path:
    return DEFAULT_BULLTARD_INBOX_ROOT / f"recap-{source_date.isoformat()}.html"


def _handle_optional_daily_error(
    stage: str,
    exc: Exception,
    *,
    strict: bool,
) -> None:
    if strict:
        raise typer.BadParameter(f"{stage}: {exc}") from exc
    typer.echo(f"{stage}_warning={exc}")


def _echo_bulltard_daily_capture_summary(result: DailyWorkflowResult) -> None:
    typer.echo(f"ranked_observation_path={result.ranked_result.observation_path}")
    typer.echo(f"ranked_row_count={result.ranked_result.row_count}")
    if result.trades_of_interest_result is None:
        typer.echo("trades_of_interest_row_count=0")
        typer.echo("trades_of_interest_symbols=")
    else:
        typer.echo(f"trades_of_interest_path={result.trades_of_interest_result.observation_path}")
        typer.echo(f"trades_of_interest_row_count={result.trades_of_interest_result.row_count}")
        typer.echo(
            f"trades_of_interest_symbols={','.join(result.trades_of_interest_result.symbols)}"
        )
    typer.echo(f"ticker_detail_success_count={len(result.ticker_results)}")
    typer.echo(f"ticker_detail_failure_count={len(result.ticker_failures)}")
    if result.ticker_failures:
        typer.echo(
            "ticker_detail_failures="
            + ",".join(f"{failure.symbol}:{failure.error}" for failure in result.ticker_failures)
        )
    typer.echo("")
    typer.echo(result.candidate_table)


def _default_outcome_start(*, snapshot_root: Path, fallback: date) -> date:
    snapshot_dates = snapshot_source_dates(
        snapshot_root=snapshot_root,
        legacy_suffix=".jsonl",
        filename=CANDIDATE_VALIDATION_SNAPSHOT_FILENAME,
    )
    return min(snapshot_dates, default=fallback)


def _echo_price_refresh_result(result: CandidatePriceRefreshResult) -> None:
    typer.echo(f"price_symbols={','.join(result.requested_symbols)}")
    typer.echo(f"price_success_count={len(result.price_results)}")
    typer.echo(f"price_failure_count={len(result.price_failures)}")
    for price_result in result.price_results:
        typer.echo(
            f"price_result={price_result.symbol} row_count={price_result.row_count} "
            f"observation_path={price_result.observation_path}"
        )
    for failure in result.price_failures:
        typer.echo(f"price_failure={failure.symbol} error={failure.error}")


def _echo_regime_price_refresh_result(result: RegimePriceRefreshResult) -> None:
    typer.echo(f"regime_price_symbols={','.join(result.requested_symbols)}")
    typer.echo(f"regime_price_success_count={len(result.price_results)}")
    typer.echo(f"regime_price_failure_count={len(result.price_failures)}")
    for price_result in result.price_results:
        typer.echo(
            f"regime_price_result={price_result.symbol} row_count={price_result.row_count} "
            f"observation_path={price_result.observation_path}"
        )
    for failure in result.price_failures:
        typer.echo(f"regime_price_failure={failure.symbol} error={failure.error}")


def _echo_market_series_fetch_results(results: tuple[MarketSeriesFetchResult, ...]) -> None:
    typer.echo("market_series_ids=" + ",".join(result.series_id for result in results))
    typer.echo(f"market_series_success_count={len(results)}")
    for result in results:
        typer.echo(
            f"market_series_result={result.series_id} row_count={result.row_count} "
            f"latest_observed_date={result.latest_observed_date.isoformat()} "
            f"latest_availability_date={result.latest_availability_date.isoformat()} "
            f"observation_path={result.observation_path}"
        )


def _echo_regime_snapshot_result(
    result: RegimeSnapshotResult,
    *,
    show_detail: bool = False,
) -> None:
    if result.snapshot_path is not None:
        typer.echo(f"regime_snapshot_path={result.snapshot_path}")
    if result.signal_snapshot_path is not None:
        typer.echo(f"market_signal_snapshot_path={result.signal_snapshot_path}")
    typer.echo(f"market_signal_count={len(result.signals)}")
    snapshot = result.snapshot
    typer.echo(f"regime_date={snapshot.source_date.isoformat()}")
    typer.echo(
        f"regime_price_date={snapshot.price_date.isoformat() if snapshot.price_date else ''}"
    )
    typer.echo(f"regime={snapshot.regime}")
    typer.echo(f"regime_score={snapshot.score}")
    typer.echo(f"regime_confidence={snapshot.confidence}")
    typer.echo(f"regime_action_state={snapshot.action_state}")
    typer.echo(f"regime_action_confidence={snapshot.action_confidence}")
    if result.pressure is not None:
        typer.echo(f"pressure_feature_count={len(result.pressure.features)}")
    typer.echo(f"market_signal_contradiction_count={len(result.contradictions)}")
    _echo_table_section(
        "overall",
        format_regime_key_signals(result),
        caption=REGIME_KEY_SIGNALS_CAPTION,
    )
    if not show_detail:
        return
    _echo_table_section(
        "market_signals",
        result.signal_table,
        caption=REGIME_MARKET_SIGNALS_CAPTION,
    )
    _echo_table_section(
        "pressure_features",
        result.pressure_table,
        caption="normalized stretch/washout setup inputs before action gating",
    )
    _echo_table_section(
        "action_evidence",
        result.action_table,
        caption="turn-signal evidence by family before final protect/redeploy action",
    )


def _echo_regime_backfill_result(result: RegimeBackfillResult) -> None:
    typer.echo(f"regime_backfill_start={result.start_date.isoformat()}")
    typer.echo(f"regime_backfill_end={result.end_date.isoformat()}")
    typer.echo(f"regime_backfill_date_count={len(result.source_dates)}")
    typer.echo(
        "regime_backfill_first_date="
        f"{result.source_dates[0].isoformat() if result.source_dates else ''}"
    )
    typer.echo(
        "regime_backfill_last_date="
        f"{result.source_dates[-1].isoformat() if result.source_dates else ''}"
    )
    typer.echo(f"regime_snapshot_count={len(result.snapshot_paths)}")
    typer.echo(f"market_signal_snapshot_count={len(result.signal_snapshot_paths)}")
    typer.echo(f"regime_backfill_skipped_existing_count={len(result.skipped_snapshot_paths)}")
    if result.snapshot_paths:
        typer.echo(f"first_regime_snapshot_path={result.snapshot_paths[0]}")
        typer.echo(f"last_regime_snapshot_path={result.snapshot_paths[-1]}")
    if result.signal_snapshot_paths:
        typer.echo(f"first_market_signal_snapshot_path={result.signal_snapshot_paths[0]}")
        typer.echo(f"last_market_signal_snapshot_path={result.signal_snapshot_paths[-1]}")


def _echo_cli_fields(fields: tuple[tuple[str, object], ...]) -> None:
    typer.echo(_format_cli_fields(fields))


def _echo_table_section(title: str, table: str | None, *, caption: str | None = None) -> None:
    text = _format_table_section(title, table, caption=caption)
    if not text:
        return
    typer.echo(text)


def _format_cli_fields(fields: tuple[tuple[str, object], ...]) -> str:
    return "\n".join(f"{name}={value}" for name, value in fields)


def _format_table_section(title: str, table: str | None, *, caption: str | None = None) -> str:
    if not table:
        return ""
    heading = f"{title}: {caption}" if caption else f"{title}:"
    return f"\n{heading}\n{table}"


def _format_outcome_tables(
    fields: tuple[tuple[str, object], ...],
    *,
    summary_table: str,
    frequency_table: str | None = None,
) -> str:
    parts = [_format_cli_fields(fields)]
    frequency = _format_table_section("frequency_table", frequency_table)
    if frequency:
        parts.append(frequency)
    parts.append(_format_table_section("summary_table", summary_table))
    return "\n".join(part for part in parts if part)


def _echo_outcome_tables(
    fields: tuple[tuple[str, object], ...],
    *,
    summary_table: str,
    frequency_table: str | None = None,
) -> None:
    typer.echo(
        _format_outcome_tables(
            fields,
            summary_table=summary_table,
            frequency_table=frequency_table,
        )
    )


def _emit_regime_outcome_report(
    report_text: str,
    *,
    save_report: bool,
    outcome_group: str,
    artifact_version: str,
    start_date: date,
    end_date: date,
    horizons: tuple[int, ...],
    snapshot_version: str | None,
) -> None:
    typer.echo(report_text)
    if not save_report:
        return
    path = regime_outcome_report_path(
        outcome_group=outcome_group,
        version=artifact_version,
    )
    saved_text = _saved_outcome_report_text(
        report_text,
        outcome_group=outcome_group,
        artifact_version=artifact_version,
        start_date=start_date,
        end_date=end_date,
        horizons=horizons,
        snapshot_version=snapshot_version,
    )
    _write_text_report(path=path, text=saved_text)
    typer.echo(f"outcome_report_path={path}")


def _saved_outcome_report_text(
    report_text: str,
    *,
    outcome_group: str,
    artifact_version: str,
    start_date: date,
    end_date: date,
    horizons: tuple[int, ...],
    snapshot_version: str | None,
) -> str:
    fields = (
        ("outcome_group", outcome_group),
        ("artifact_version", artifact_version),
        ("snapshot_version", snapshot_version or artifact_version),
        ("outcome_start", start_date.isoformat()),
        ("outcome_end", end_date.isoformat()),
        ("outcome_horizons", ",".join(str(horizon) for horizon in horizons)),
        ("generated_at", datetime.now(UTC).isoformat(timespec="seconds")),
        (
            "command",
            "marketlab regime outcomes "
            f"--by {outcome_group} "
            f"--start {start_date.isoformat()} "
            f"--end {end_date.isoformat()} "
            f"--horizons {','.join(str(horizon) for horizon in horizons)}",
        ),
    )
    return f"{_format_cli_fields(fields)}\n\n{report_text.rstrip()}\n"


def _write_text_report(*, path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise typer.BadParameter(f"Failed to write outcome report: {path}") from exc


def _outcome_artifact_version(
    *,
    outcome_group: RegimeOutcomeGroup,
    snapshot_version: str | None,
) -> str:
    if snapshot_version is not None:
        return snapshot_version
    if outcome_group == RegimeOutcomeGroup.POLICY:
        return POLICY_SNAPSHOT_VERSION
    return REGIME_SNAPSHOT_VERSION


def _echo_regime_outcome_result(result: RegimeOutcomeResult) -> None:
    typer.echo(_regime_outcome_report_text(result))


def _regime_outcome_report_text(result: RegimeOutcomeResult) -> str:
    return _format_outcome_tables(
        (
            ("regime_outcome_count", len(result.outcomes)),
            ("available_regime_outcome_count", _available_regime_outcome_count(result)),
        ),
        summary_table=result.table,
    )


def _echo_regime_action_outcome_result(result: RegimeActionOutcomeResult) -> None:
    typer.echo(_regime_action_outcome_report_text(result))


def _regime_action_outcome_report_text(result: RegimeActionOutcomeResult) -> str:
    return _format_outcome_tables(
        (
            ("regime_action_count", len(result.actions)),
            ("regime_action_outcome_count", len(result.outcomes)),
            (
                "available_regime_action_outcome_count",
                _available_regime_action_outcome_count(result),
            ),
        ),
        frequency_table=result.frequency_table,
        summary_table=result.table,
    )


def _regime_posture_outcome_report_text(result: RegimePostureOutcomeResult) -> str:
    return _format_outcome_tables(
        (
            ("regime_posture_count", len(result.postures)),
            ("regime_posture_outcome_count", len(result.outcomes)),
            (
                "available_regime_posture_outcome_count",
                _available_regime_posture_outcome_count(result),
            ),
        ),
        frequency_table=result.frequency_table,
        summary_table=result.table,
    )


def _regime_redeploy_outcome_report_text(result: RegimeRedeployOutcomeResult) -> str:
    return _format_outcome_tables(
        (
            ("regime_redeploy_outcome_count", len(result.outcomes)),
            (
                "available_regime_redeploy_outcome_count",
                _available_regime_redeploy_outcome_count(result),
            ),
        ),
        summary_table=result.table,
    )


def _regime_protect_outcome_report_text(
    result: RegimeProtectOutcomeResult,
    cluster_result: RegimeProtectClusterResult,
) -> str:
    fields = _format_cli_fields(
        (
            ("regime_protect_outcome_count", len(result.outcomes)),
            (
                "available_regime_protect_outcome_count",
                _available_regime_protect_outcome_count(result),
            ),
            ("regime_protect_cluster_count", _protect_cluster_count(cluster_result)),
            ("regime_protect_cluster_outcome_count", len(cluster_result.outcomes)),
            (
                "false_alert_cluster_outcome_count",
                _false_alert_cluster_outcome_count(cluster_result),
            ),
        )
    )
    return "\n\n".join(
        (
            fields,
            _format_table_section("protect_gate_summary", result.table),
            _format_table_section("protect_cluster_summary", cluster_result.table),
        )
    )


def _echo_regime_pressure_outcome_result(result: RegimePressureOutcomeResult) -> None:
    typer.echo(_regime_pressure_outcome_report_text(result))


def _regime_pressure_outcome_report_text(result: RegimePressureOutcomeResult) -> str:
    return _format_outcome_tables(
        (
            ("regime_pressure_count", len(result.pressures)),
            ("regime_pressure_outcome_count", len(result.outcomes)),
            (
                "available_regime_pressure_outcome_count",
                _available_regime_pressure_outcome_count(result),
            ),
        ),
        summary_table=result.table,
    )


def _regime_correction_episode_report_text(
    result: RegimeCorrectionEpisodeResult,
) -> str:
    return _format_outcome_tables(
        (
            ("regime_correction_episode_count", len(result.episodes)),
            (
                "regime_correction_episode_protect_count",
                _protected_correction_episode_count(result),
            ),
        ),
        summary_table=result.table,
    )


def _echo_store_refresh_result(result: StoreRefreshResult) -> None:
    typer.echo(f"research_db_path={result.db_path}")
    typer.echo(f"research_store_schema={result.schema_version}")
    typer.echo("")
    typer.echo(format_store_refresh_result(result))


def _echo_policy_snapshot_result(
    result: PortfolioPolicySnapshotResult,
    *,
    show_detail: bool = False,
) -> None:
    if result.snapshot_path is not None:
        typer.echo(f"policy_snapshot_path={result.snapshot_path}")
    snapshot = result.snapshot
    typer.echo(f"policy_date={snapshot.source_date.isoformat()}")
    typer.echo(f"policy_state={snapshot.policy_state}")
    typer.echo(f"policy_confidence={snapshot.policy_confidence}")
    typer.echo(f"marginal_beta_target={snapshot.marginal_beta_target:.2f}")
    typer.echo(f"regime={snapshot.regime}")
    typer.echo(f"regime_action_state={snapshot.regime_action_state}")
    typer.echo(f"candidate_count={snapshot.candidate_count}")
    typer.echo(f"confirm_candidate_count={snapshot.confirm_candidate_count}")
    if not show_detail:
        return
    typer.echo("")
    typer.echo(result.table)


def _echo_policy_backfill_result(result: PortfolioPolicyBackfillResult) -> None:
    typer.echo(f"policy_backfill_start={result.start_date.isoformat()}")
    typer.echo(f"policy_backfill_end={result.end_date.isoformat()}")
    typer.echo(f"policy_backfill_date_count={len(result.source_dates)}")
    typer.echo(
        "policy_backfill_first_date="
        f"{result.source_dates[0].isoformat() if result.source_dates else ''}"
    )
    typer.echo(
        "policy_backfill_last_date="
        f"{result.source_dates[-1].isoformat() if result.source_dates else ''}"
    )
    typer.echo(f"policy_snapshot_count={len(result.snapshot_paths)}")
    if result.snapshot_paths:
        typer.echo(f"first_policy_snapshot_path={result.snapshot_paths[0]}")
        typer.echo(f"last_policy_snapshot_path={result.snapshot_paths[-1]}")


def _echo_policy_outcome_result(result: PortfolioPolicyOutcomeResult) -> None:
    typer.echo(_policy_outcome_report_text(result))


def _policy_outcome_report_text(result: PortfolioPolicyOutcomeResult) -> str:
    return _format_outcome_tables(
        (
            ("portfolio_policy_count", len(result.policies)),
            ("portfolio_policy_outcome_count", len(result.outcomes)),
            (
                "available_portfolio_policy_outcome_count",
                _available_policy_outcome_count(result),
            ),
        ),
        frequency_table=result.frequency_table,
        summary_table=result.table,
    )


def _echo_daily_policy_report_result(result: DailyPolicyReportResult) -> None:
    if result.policy_snapshot_path is not None:
        typer.echo(f"policy_snapshot_path={result.policy_snapshot_path}")
        typer.echo("")
    typer.echo(result.report)


def _echo_regime_recent_report_result(result: RegimeRecentReportResult) -> None:
    typer.echo(result.report)


def _echo_regime_export_result(result: RegimeExportResult) -> None:
    typer.echo(f"xlsx_path={result.workbook_path}")
    typer.echo(f"csv_path={result.csv_path}")
    typer.echo(f"export_start={result.start_date.isoformat()}")
    typer.echo(f"export_end={result.end_date.isoformat()}")
    typer.echo(f"export_row_count={result.row_count}")
    typer.echo(f"export_column_count={result.column_count}")


def _echo_market_signal_outcome_result(result: MarketSignalOutcomeResult) -> None:
    typer.echo(_market_signal_outcome_report_text(result))


def _market_signal_outcome_report_text(result: MarketSignalOutcomeResult) -> str:
    return _format_outcome_tables(
        (
            ("market_signal_outcome_count", len(result.outcomes)),
            (
                "available_market_signal_outcome_count",
                _available_market_signal_outcome_count(result),
            ),
        ),
        summary_table=result.table,
    )


def _available_candidate_outcome_count(result: CandidateOutcomeResult) -> int:
    return sum(1 for outcome in result.outcomes if outcome.return_value is not None)


def _available_regime_outcome_count(result: RegimeOutcomeResult) -> int:
    return sum(
        1
        for outcome in result.outcomes
        if outcome.spy_return is not None and outcome.qqq_return is not None
    )


def _available_regime_action_outcome_count(result: RegimeActionOutcomeResult) -> int:
    return sum(
        1
        for outcome in result.outcomes
        if outcome.spy_return is not None and outcome.qqq_return is not None
    )


def _available_regime_posture_outcome_count(result: RegimePostureOutcomeResult) -> int:
    return sum(
        1
        for outcome in result.outcomes
        if outcome.spy_return is not None and outcome.qqq_return is not None
    )


def _available_regime_redeploy_outcome_count(result: RegimeRedeployOutcomeResult) -> int:
    return sum(
        1
        for outcome in result.outcomes
        if outcome.spy_return is not None and outcome.qqq_return is not None
    )


def _available_regime_protect_outcome_count(result: RegimeProtectOutcomeResult) -> int:
    return sum(
        1
        for outcome in result.outcomes
        if outcome.spy_return is not None and outcome.qqq_return is not None
    )


def _protect_cluster_count(result: RegimeProtectClusterResult) -> int:
    return len({outcome.cluster_start_date for outcome in result.outcomes})


def _false_alert_cluster_outcome_count(result: RegimeProtectClusterResult) -> int:
    return sum(1 for outcome in result.outcomes if outcome.had_5pct_drawdown is False)


def _available_regime_pressure_outcome_count(result: RegimePressureOutcomeResult) -> int:
    return sum(
        1
        for outcome in result.outcomes
        if outcome.spy_return is not None and outcome.qqq_return is not None
    )


def _protected_correction_episode_count(result: RegimeCorrectionEpisodeResult) -> int:
    return sum(1 for episode in result.episodes if episode.first_protect_date is not None)


def _available_market_signal_outcome_count(result: MarketSignalOutcomeResult) -> int:
    return sum(
        1
        for outcome in result.outcomes
        if outcome.spy_return is not None and outcome.qqq_return is not None
    )


def _available_policy_outcome_count(result: PortfolioPolicyOutcomeResult) -> int:
    return sum(1 for outcome in result.outcomes if outcome.benchmark_return is not None)


def _format_validation_summary(
    summary: CandidateValidationSummary,
    *,
    prefix: str = "validation_summary",
) -> str:
    return (
        f"{prefix}=candidates:{summary.candidate_count} "
        f"confirm:{summary.confirm_count} watch:{summary.watch_count} "
        f"avoid:{summary.avoid_count} missing_price:{summary.missing_price_count} "
        f"thin_underlying:{summary.thin_underlying_count}"
    )


if __name__ == "__main__":
    app()
