"""Command-line entrypoint for MarketLab."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path

import typer
from loguru import logger

from marketlab import __version__
from marketlab.bulltard.ingest import (
    DEFAULT_DEBUG_ROOT,
    DEFAULT_OBSERVATIONS_ROOT,
    IngestError,
    build_ingest_plan,
    ingest_planned_view,
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

    try:
        source_date = date.fromisoformat(source_date_value)
    except ValueError as exc:
        raise typer.BadParameter("Date must use YYYY-MM-DD format", param_hint="--date") from exc

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


if __name__ == "__main__":
    app()
