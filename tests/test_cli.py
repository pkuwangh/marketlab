from typer.testing import CliRunner

from marketlab import __version__
from marketlab.cli import app, main


def test_typer_app_has_no_args_is_help_enabled() -> None:
    assert app.info.no_args_is_help is True


def test_console_entrypoint_no_args_shows_help(capsys) -> None:
    exit_code = main([])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "MarketLab research workflow CLI." in captured.out
    assert "--version" in captured.out


def test_typer_no_args_shows_help() -> None:
    result = CliRunner().invoke(app, [])

    assert result.exit_code != 0
    assert "MarketLab research workflow CLI." in result.output
    assert "--version" in result.output


def test_version_option() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert f"marketlab {__version__}" in result.output
