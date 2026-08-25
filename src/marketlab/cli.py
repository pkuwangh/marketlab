"""Command-line entrypoint for MarketLab."""

from __future__ import annotations

import sys

import typer

from marketlab import __version__

app = typer.Typer(
    help="MarketLab research workflow CLI.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"marketlab {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the application version and exit.",
    ),
) -> None:
    """Run MarketLab research workflows."""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        args = ["--help"]
    try:
        app(args=args, prog_name="marketlab", standalone_mode=False)
    except typer.Exit as exc:
        return int(exc.exit_code or 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
