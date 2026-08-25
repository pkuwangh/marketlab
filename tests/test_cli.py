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
    assert "Bulltard source capture and parsing utilities." in result.output
    assert "inspect-recap" in result.output
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


def test_bulltard_archive_local_outputs_manifest_path(tmp_path: Path) -> None:
    output_root = tmp_path / "raw" / "bulltard"

    result = CliRunner().invoke(
        app,
        [
            "bulltard",
            "archive-local",
            "--date",
            "2026-08-24",
            "--artifact",
            f"recap={FIXTURE_DIR / 'recap.html'}",
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0
    assert str(output_root / "2026-08-24" / "capture_manifest.json") in result.output
    assert (output_root / "2026-08-24" / "recap.html").is_file()
