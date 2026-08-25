from datetime import date
from pathlib import Path

import pytest

from marketlab.bulltard.archive import (
    ArchiveError,
    LocalArtifactInput,
    archive_local_artifacts,
    parse_local_artifact_arg,
)
from marketlab.bulltard.models import CaptureManifest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bulltard"


def test_parse_local_artifact_arg() -> None:
    artifact = parse_local_artifact_arg("recap=tests/fixtures/bulltard/recap.html")

    assert artifact.route_name == "recap"
    assert artifact.source_path == Path("tests/fixtures/bulltard/recap.html")


def test_parse_local_artifact_arg_rejects_missing_separator() -> None:
    with pytest.raises(ArchiveError, match="route_name=path"):
        parse_local_artifact_arg("recap")


def test_archive_local_artifacts_writes_payload_and_manifest(tmp_path: Path) -> None:
    source_path = FIXTURE_DIR / "recap.html"
    output_root = tmp_path / "raw" / "bulltard"

    manifest = archive_local_artifacts(
        source_date=date(2026, 8, 24),
        artifacts=(LocalArtifactInput(route_name="recap", source_path=source_path),),
        output_root=output_root,
    )

    output_dir = output_root / "2026-08-24"
    archived_recap = output_dir / "recap.html"
    manifest_path = output_dir / "capture_manifest.json"

    assert archived_recap.read_bytes() == source_path.read_bytes()
    assert manifest_path.is_file()
    assert manifest.artifacts[0].route_name == "recap"
    assert manifest.artifacts[0].path == str(archived_recap)
    assert manifest.artifacts[0].source_url == str(source_path)
    assert manifest.artifacts[0].status_code is None

    restored = CaptureManifest.from_json(manifest_path.read_text(encoding="utf-8"))
    assert restored == manifest


def test_archive_local_artifacts_refuses_existing_manifest(tmp_path: Path) -> None:
    source_path = FIXTURE_DIR / "recap.html"
    output_root = tmp_path / "raw" / "bulltard"
    artifact = LocalArtifactInput(route_name="recap", source_path=source_path)

    archive_local_artifacts(
        source_date=date(2026, 8, 24),
        artifacts=(artifact,),
        output_root=output_root,
    )

    with pytest.raises(ArchiveError, match="Refusing to overwrite existing manifest"):
        archive_local_artifacts(
            source_date=date(2026, 8, 24),
            artifacts=(artifact,),
            output_root=output_root,
        )


def test_archive_local_artifacts_force_overwrites(tmp_path: Path) -> None:
    source_path = FIXTURE_DIR / "recap.html"
    output_root = tmp_path / "raw" / "bulltard"
    artifact = LocalArtifactInput(route_name="recap", source_path=source_path)

    archive_local_artifacts(
        source_date=date(2026, 8, 24),
        artifacts=(artifact,),
        output_root=output_root,
    )
    manifest = archive_local_artifacts(
        source_date=date(2026, 8, 24),
        artifacts=(artifact,),
        output_root=output_root,
        force=True,
    )

    assert manifest.artifacts[0].route_name == "recap"
