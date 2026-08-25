"""Command-line entrypoint for MarketLab."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path

import typer
from loguru import logger

from marketlab import __version__
from marketlab.bulltard.archive import (
    DEFAULT_OUTPUT_ROOT,
    ArchiveError,
    archive_local_artifacts,
    parse_local_artifact_arg,
)
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


@bulltard_app.command("archive-local")
def archive_local(
    source_date_value: str = typer.Option(
        ...,
        "--date",
        metavar="YYYY-MM-DD",
        help="Source date represented by the local artifacts.",
    ),
    artifact_args: list[str] = typer.Option(
        ...,
        "--artifact",
        "-a",
        help="Artifact to archive, in the form route_name=path.",
    ),
    output_root: Path = typer.Option(
        DEFAULT_OUTPUT_ROOT,
        "--output-root",
        file_okay=False,
        help="Root directory for raw Bulltard archives.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite an existing local archive for this date.",
    ),
) -> None:
    """Archive already-saved local Bulltard artifacts and write a manifest."""

    try:
        source_date = date.fromisoformat(source_date_value)
    except ValueError as exc:
        raise typer.BadParameter("Date must use YYYY-MM-DD format", param_hint="--date") from exc

    try:
        artifacts = [parse_local_artifact_arg(value) for value in artifact_args]
        manifest = archive_local_artifacts(
            source_date=source_date,
            artifacts=artifacts,
            output_root=output_root,
            force=force,
        )
    except ArchiveError as exc:
        raise typer.BadParameter(str(exc)) from exc

    manifest_path = output_root / source_date.isoformat() / "capture_manifest.json"
    typer.echo(str(manifest_path))
    logger.bind(
        source_date=source_date.isoformat(),
        manifest_path=str(manifest_path),
        artifact_count=len(manifest.artifacts),
    ).success("Archived local Bulltard capture")


if __name__ == "__main__":
    app()
