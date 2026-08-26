"""Command-line entrypoint for MarketLab."""

from __future__ import annotations

from datetime import date
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
from marketlab.bulltard.daily import DailyWorkflowError, run_daily_workflow
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
from marketlab.bulltard.recaps import SignedSourceUrlError, extract_signed_source_url
from marketlab.logging import configure_logging


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
app.add_typer(bulltard_app, name="bulltard")


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


def _parse_source_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter("Date must use YYYY-MM-DD format", param_hint="--date") from exc


def _parse_extra_tickers(value: str) -> tuple[str, ...]:
    return tuple(symbol.strip() for symbol in value.split(",") if symbol.strip())


if __name__ == "__main__":
    app()
