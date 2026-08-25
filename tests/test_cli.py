from pathlib import Path

from typer.testing import CliRunner

from marketlab import __version__
from marketlab.cli import app, bulltard_app

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bulltard"


def test_typer_app_has_no_args_is_help_enabled() -> None:
    assert app.info.no_args_is_help is True
    assert bulltard_app.info.no_args_is_help is True


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
    assert "Prepare a targeted Bulltard ingest run" in result.output
    assert "recap_path" in result.output
    assert "--date" in result.output
    assert "Missing option" not in result.output
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


def test_bulltard_ingest_prepares_first_view(tmp_path: Path) -> None:
    output_root = tmp_path / "observations" / "bulltard"

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
        ],
    )

    assert result.exit_code == 0
    assert "view=ranked-option-trades" in result.output
    assert "route_path=/ranked_option_trades" in result.output
    assert "jamesbulltard.substack.com/redirect" in result.output
    assert "fixture-secret" in result.output
    assert str(output_root / "ranked_option_trades" / "2026-08-24.jsonl") in result.output
