"""Command-line entrypoint for MarketLab."""

from __future__ import annotations

from datetime import date, timedelta
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
from marketlab.bulltard.recaps import SignedSourceUrlError, extract_signed_source_url
from marketlab.bulltard.validation import (
    DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
    DEFAULT_MIN_DOLLAR_VOLUME,
    CandidateValidationError,
    CandidateValidationSummary,
    validate_bulltard_candidates,
)
from marketlab.logging import configure_logging
from marketlab.market_signals import DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT
from marketlab.prices import (
    DEFAULT_PRICE_OBSERVATIONS_ROOT,
    PriceDataError,
    fetch_and_write_stooq_daily_prices,
    fetch_and_write_yahoo_daily_prices,
    import_daily_price_csv,
)
from marketlab.regime import (
    DEFAULT_REGIME_SNAPSHOT_ROOT,
    RegimeError,
    RegimeOutcomeResult,
    RegimePriceRefreshResult,
    RegimeSnapshotResult,
    compute_regime_outcomes,
    compute_regime_snapshot,
    refresh_regime_prices,
)


class LogLevel(StrEnum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


app = typer.Typer(
    help="MarketLab research workflow CLI.",
    no_args_is_help=True,
)
bulltard_app = typer.Typer(
    help="Bulltard link extraction and ingest utilities.",
    no_args_is_help=True,
)
prices_app = typer.Typer(
    help="Daily OHLCV price utilities.",
    no_args_is_help=True,
)
regime_app = typer.Typer(
    help="Market regime utilities.",
    no_args_is_help=True,
)
app.add_typer(bulltard_app, name="bulltard")
app.add_typer(prices_app, name="prices")
app.add_typer(regime_app, name="regime")

DEFAULT_DAILY_PRICE_LOOKBACK_DAYS = 550
DEFAULT_OUTCOME_HORIZONS_VALUE = "1,5,20,40,65,126"


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
        help="Also refresh Yahoo daily prices for regime proxies.",
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
        help="Last price date for --fetch-prices. Defaults to today.",
    ),
    price_root: Path = typer.Option(
        DEFAULT_PRICE_OBSERVATIONS_ROOT,
        "--price-root",
        file_okay=False,
        help="Root directory containing daily price observations.",
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
    write_snapshot: bool = typer.Option(
        True,
        "--write/--no-write",
        help="Write the market regime snapshot.",
    ),
) -> None:
    """Compute a market regime snapshot from price proxies."""

    source_date = _parse_source_date(source_date_value)
    if fetch_prices_flag:
        price_start = (
            _parse_date_option(price_start_value, option_name="--price-start")
            if price_start_value
            else source_date - timedelta(days=DEFAULT_DAILY_PRICE_LOOKBACK_DAYS)
        )
        price_end = (
            _parse_date_option(price_end_value, option_name="--price-end")
            if price_end_value
            else date.today()
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

    try:
        result = compute_regime_snapshot(
            source_date=source_date,
            price_root=price_root,
            snapshot_root=snapshot_root,
            signal_snapshot_root=signal_snapshot_root,
            write_snapshot=write_snapshot,
        )
    except RegimeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _echo_regime_snapshot_result(result)


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
) -> None:
    """Replay forward SPY/QQQ outcomes for saved market regimes."""

    start_date = _parse_date_option(start_date_value, option_name="--start")
    end_date = _parse_date_option(end_date_value, option_name="--end")
    try:
        result = compute_regime_outcomes(
            start_date=start_date,
            end_date=end_date,
            snapshot_root=snapshot_root,
            price_root=price_root,
            horizons=_parse_horizons(horizons_value),
        )
    except RegimeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    _echo_regime_outcome_result(result)


@bulltard_app.command("inspect-recap", no_args_is_help=True)
def inspect_recap(
    recap_path: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local recap text or HTML file.",
    ),
) -> None:
    """Extract the signed Bulltard source URL from a local recap."""

    try:
        logger.bind(path=str(recap_path)).info("Reading Bulltard recap")
        signed_url = extract_signed_source_url(recap_path.read_text(encoding="utf-8"))
    except SignedSourceUrlError as exc:
        raise typer.BadParameter(str(exc), param_hint="recap_path") from exc

    typer.echo(signed_url)
    logger.bind(path=str(recap_path), url=signed_url).success("Inspected Bulltard recap")


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
    typer.echo(f"signed_url={plan.signed_url}")
    typer.echo(f"final_url={result.fetched_view.final_url}")
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
    typer.echo(f"signed_url={result.fetched_page.signed_url}")
    typer.echo(f"final_url={result.fetched_page.final_url}")
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
        help="Last price date for --fetch-prices. Defaults to today.",
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
            else date.today()
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


def _default_outcome_start(*, snapshot_root: Path, fallback: date) -> date:
    snapshot_dates = []
    for pattern in ("*.jsonl", "*.json"):
        for path in snapshot_root.glob(pattern):
            try:
                snapshot_dates.append(date.fromisoformat(path.stem))
            except ValueError:
                continue
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


def _echo_regime_snapshot_result(result: RegimeSnapshotResult) -> None:
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
    typer.echo(f"missing_regime_symbols={','.join(snapshot.missing_symbols)}")
    if result.signal_table:
        typer.echo("")
        typer.echo(result.signal_table)
    typer.echo("")
    typer.echo(result.table)


def _echo_regime_outcome_result(result: RegimeOutcomeResult) -> None:
    typer.echo(f"regime_outcome_count={len(result.outcomes)}")
    typer.echo(f"available_regime_outcome_count={_available_regime_outcome_count(result)}")
    typer.echo("")
    typer.echo(result.table)


def _available_candidate_outcome_count(result: CandidateOutcomeResult) -> int:
    return sum(1 for outcome in result.outcomes if outcome.return_value is not None)


def _available_regime_outcome_count(result: RegimeOutcomeResult) -> int:
    return sum(
        1
        for outcome in result.outcomes
        if outcome.spy_return is not None and outcome.qqq_return is not None
    )


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
