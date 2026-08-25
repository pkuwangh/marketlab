"""Command-line entrypoint for MarketLab."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import typer
from loguru import logger

from marketlab import __version__
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
    help="Bulltard source capture and parsing utilities.",
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


@bulltard_app.command("inspect-recap")
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


if __name__ == "__main__":
    app()
