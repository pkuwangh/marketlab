"""Archive local Bulltard source artifacts into the raw data layout."""

from __future__ import annotations

import hashlib
import mimetypes
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from loguru import logger

from marketlab.bulltard.models import CaptureManifest, CaptureStatus, RawArtifact

DEFAULT_CAPTURE_VERSION = "bulltard_local_archive_v0"
DEFAULT_OUTPUT_ROOT = Path("data/raw/bulltard")
_ROUTE_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


class ArchiveError(ValueError):
    """Raised when local artifacts cannot be archived deterministically."""


@dataclass(frozen=True, slots=True)
class LocalArtifactInput:
    """One local source artifact to copy into the raw Bulltard archive."""

    route_name: str
    source_path: Path


def parse_local_artifact_arg(value: str) -> LocalArtifactInput:
    """Parse a CLI artifact argument in the form `route_name=path`."""

    route_name, separator, path = value.partition("=")
    if not separator:
        raise ArchiveError("Artifact must be in the form route_name=path")
    if not route_name:
        raise ArchiveError("Artifact route_name is required")
    if not path:
        raise ArchiveError("Artifact path is required")
    _validate_route_name(route_name)
    return LocalArtifactInput(route_name=route_name, source_path=Path(path))


def archive_local_artifacts(
    *,
    source_date: date,
    artifacts: Sequence[LocalArtifactInput],
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    capture_version: str = DEFAULT_CAPTURE_VERSION,
    force: bool = False,
) -> CaptureManifest:
    """Copy local artifacts into a dated raw directory and write a capture manifest."""

    if not artifacts:
        raise ArchiveError("At least one artifact is required")

    output_dir = output_root / source_date.isoformat()
    manifest_path = output_dir / "capture_manifest.json"
    planned = _plan_archive(output_dir=output_dir, artifacts=artifacts)

    if manifest_path.exists() and not force:
        raise ArchiveError(f"Refusing to overwrite existing manifest: {manifest_path}")

    collisions = [destination for _artifact, destination in planned if destination.exists()]
    if collisions and not force:
        paths = ", ".join(str(path) for path in collisions)
        raise ArchiveError(f"Refusing to overwrite existing artifact(s): {paths}")

    logger.bind(
        source_date=source_date.isoformat(),
        artifact_count=len(planned),
        output_dir=str(output_dir),
        force=force,
    ).info("Archiving local Bulltard artifacts")

    output_dir.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(UTC)
    raw_artifacts: list[RawArtifact] = []

    for artifact, destination in planned:
        payload = artifact.source_path.read_bytes()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        raw_artifact = RawArtifact(
            route_name=artifact.route_name,
            path=str(destination),
            source_url=str(artifact.source_path),
            final_url=str(artifact.source_path),
            status=CaptureStatus.OK,
            status_code=None,
            content_type=_guess_content_type(destination),
            captured_at=captured_at,
            sha256=hashlib.sha256(payload).hexdigest(),
            byte_count=len(payload),
        )
        raw_artifacts.append(raw_artifact)
        logger.bind(
            route_name=artifact.route_name,
            source_path=str(artifact.source_path),
            destination=str(destination),
            byte_count=len(payload),
            sha256=raw_artifact.sha256,
        ).success("Archived local Bulltard artifact")

    manifest = CaptureManifest(
        source_date=source_date,
        capture_version=capture_version,
        created_at=captured_at,
        artifacts=tuple(raw_artifacts),
    )
    manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    logger.bind(path=str(manifest_path), artifact_count=len(raw_artifacts)).success(
        "Wrote Bulltard capture manifest"
    )
    return manifest


def _plan_archive(
    *,
    output_dir: Path,
    artifacts: Sequence[LocalArtifactInput],
) -> tuple[tuple[LocalArtifactInput, Path], ...]:
    seen_routes: set[str] = set()
    seen_destinations: set[Path] = set()
    planned: list[tuple[LocalArtifactInput, Path]] = []

    for artifact in artifacts:
        _validate_route_name(artifact.route_name)
        if artifact.route_name in seen_routes:
            raise ArchiveError(f"Duplicate artifact route_name: {artifact.route_name}")
        seen_routes.add(artifact.route_name)

        if not artifact.source_path.is_file():
            raise ArchiveError(
                f"Artifact path does not exist or is not a file: {artifact.source_path}"
            )

        destination = output_dir / _artifact_filename(artifact)
        if destination in seen_destinations:
            raise ArchiveError(f"Duplicate artifact destination: {destination}")
        seen_destinations.add(destination)
        planned.append((artifact, destination))

    return tuple(planned)


def _artifact_filename(artifact: LocalArtifactInput) -> str:
    suffix = artifact.source_path.suffix or ".html"
    return f"{artifact.route_name}{suffix}"


def _validate_route_name(route_name: str) -> None:
    if not _ROUTE_NAME_RE.fullmatch(route_name):
        raise ArchiveError(
            "Artifact route_name may contain only letters, numbers, underscores, dots, colons, "
            f"and hyphens: {route_name}"
        )


def _guess_content_type(path: Path) -> str | None:
    content_type, _encoding = mimetypes.guess_type(path)
    return content_type
