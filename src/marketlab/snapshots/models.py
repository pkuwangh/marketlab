"""Point-in-time snapshot identifiers and immutable snapshot helpers."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Self


class SignalTime(StrEnum):
    """Canonical time modes for official and provisional research signals."""

    PRIOR_CLOSE = "prior_close"
    INTRADAY_PREVIEW = "intraday_preview"
    EOD = "eod"


def signal_time_value(signal_time: SignalTime | str) -> str:
    """Normalize a signal-time value for persisted snapshot payloads."""

    return signal_time.value if isinstance(signal_time, SignalTime) else str(signal_time)


def require_eod_signal_time(
    signal_time: SignalTime | str,
    *,
    workflow: str,
) -> str:
    """Return normalized EOD signal time or reject date-level provisional timing."""

    signal_time_text = signal_time_value(signal_time)
    if signal_time_text != SignalTime.EOD.value:
        raise ValueError(
            f"{workflow} supports only signal_time=eod for date-level observations; "
            f"got {signal_time_text!r}. Add timestamp-aware inputs before using "
            "prior_close or intraday_preview."
        )
    return signal_time_text


def default_snapshot_version(
    signal_date: date,
    *,
    signal_time: SignalTime | str = SignalTime.EOD,
) -> str:
    """Return the default official snapshot-version label for one signal date."""

    return f"{signal_date.isoformat()}_{signal_time_value(signal_time)}"


def versioned_snapshot_path(
    *,
    snapshot_root: Path,
    source_date: date,
    signal_time: SignalTime | str,
    snapshot_version: str | None,
    artifact_version: str,
    filename: str,
) -> Path:
    """Return the canonical versioned path for one snapshot artifact."""

    signal_time_text = signal_time_value(signal_time)
    snapshot_version_text = snapshot_version or default_snapshot_version(
        source_date,
        signal_time=signal_time_text,
    )
    return (
        snapshot_root
        / source_date.isoformat()
        / _path_component(signal_time_text, field_name="signal_time")
        / _path_component(snapshot_version_text, field_name="snapshot_version")
        / _path_component(artifact_version, field_name="artifact_version")
        / _path_component(filename, field_name="filename")
    )


def resolve_snapshot_path(
    *,
    snapshot_root: Path,
    source_date: date,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
    artifact_version: str | None = None,
    filename: str,
    legacy_suffix: str,
) -> Path | None:
    """Resolve a snapshot path, preferring canonical files over legacy flat files."""

    candidates = find_snapshot_paths(
        snapshot_root=snapshot_root,
        source_date=source_date,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
        artifact_version=artifact_version,
        filename=filename,
    )
    if len(candidates) > 1 and artifact_version is None:
        versions = ", ".join(path.parent.name for path in candidates)
        raise ValueError(
            "Multiple snapshot artifact versions found for "
            f"{snapshot_root} {source_date.isoformat()} "
            f"{signal_time_value(signal_time)} {filename}: {versions}. "
            "Specify artifact_version explicitly."
        )
    if candidates:
        return candidates[-1]

    if (
        snapshot_version is None
        and artifact_version is None
        and signal_time_value(signal_time) == SignalTime.EOD.value
    ):
        legacy_path = snapshot_root / f"{source_date.isoformat()}{legacy_suffix}"
        if legacy_path.is_file():
            return legacy_path
    return None


def find_snapshot_paths(
    *,
    snapshot_root: Path,
    source_date: date,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
    artifact_version: str | None = None,
    filename: str,
) -> tuple[Path, ...]:
    """Find canonical snapshot files for one date/version tuple."""

    snapshot_version_text = snapshot_version or default_snapshot_version(
        source_date,
        signal_time=signal_time,
    )
    base_path = (
        snapshot_root
        / source_date.isoformat()
        / _path_component(signal_time_value(signal_time), field_name="signal_time")
        / _path_component(snapshot_version_text, field_name="snapshot_version")
    )
    if artifact_version is not None:
        path = (
            base_path / _path_component(artifact_version, field_name="artifact_version") / filename
        )
        return (path,) if path.is_file() else ()
    if not base_path.is_dir():
        return ()
    return tuple(sorted(path for path in base_path.glob(f"*/{filename}") if path.is_file()))


def snapshot_source_dates(
    *,
    snapshot_root: Path,
    legacy_suffix: str,
    filename: str,
) -> tuple[date, ...]:
    """Return source dates present in legacy or canonical snapshot layouts."""

    if not snapshot_root.exists():
        return ()
    source_dates: set[date] = set()
    for path in snapshot_root.glob(f"*{legacy_suffix}"):
        try:
            source_dates.add(date.fromisoformat(path.stem))
        except ValueError:
            continue
    for path in snapshot_root.rglob(filename):
        try:
            source_dates.add(date.fromisoformat(path.relative_to(snapshot_root).parts[0]))
        except (IndexError, ValueError):
            continue
    return tuple(sorted(source_dates))


def utc_timestamp() -> str:
    """Return a compact UTC timestamp for provenance fields."""

    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _path_component(value: str, *, field_name: str) -> str:
    text = str(value).strip()
    if not text or text in {".", ".."} or "/" in text or "\\" in text:
        raise ValueError(f"Invalid {field_name}: {value!r}")
    return text


def current_code_revision(*, repo_root: Path | None = None) -> str | None:
    """Best-effort git revision for persisted research provenance."""

    try:
        result = subprocess.run(
            ("git", "rev-parse", "--short", "HEAD"),
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    return revision or None


VOLATILE_PROVENANCE_FIELDS = frozenset({"created_at", "retrieved_at", "code_revision"})


def write_immutable_payload(
    *,
    path: Path,
    payload: str,
    error_cls: type[Exception] = ValueError,
    overwrite: bool = False,
) -> bool:
    """Write a snapshot payload without silently replacing different history.

    Returns True when the file was written and False when an existing equivalent
    payload was kept. The volatile creation timestamp is ignored for equivalence
    so idempotent reruns do not rewrite the original timestamp.
    """

    if path.is_file():
        try:
            existing_payload = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise error_cls(f"Failed to read existing snapshot: {path}") from exc
        if existing_payload == payload or _json_payloads_equal(
            existing_payload,
            payload,
            ignored_fields=VOLATILE_PROVENANCE_FIELDS,
        ):
            return False
        if not overwrite:
            raise error_cls(
                f"Refusing to overwrite existing historical snapshot with different content: {path}"
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(payload, encoding="utf-8")
    except OSError as exc:
        raise error_cls(f"Failed to write snapshot: {path}") from exc
    return True


def _json_payloads_equal(
    left: str,
    right: str,
    *,
    ignored_fields: frozenset[str],
) -> bool:
    try:
        return _normalized_json_lines(left, ignored_fields) == _normalized_json_lines(
            right,
            ignored_fields,
        )
    except (json.JSONDecodeError, TypeError):
        return False


def _normalized_json_lines(
    payload: str,
    ignored_fields: frozenset[str],
) -> tuple[Any, ...]:
    return tuple(
        _drop_ignored_fields(json.loads(line), ignored_fields)
        for line in payload.splitlines()
        if line.strip()
    )


def _drop_ignored_fields(value: Any, ignored_fields: frozenset[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _drop_ignored_fields(item, ignored_fields)
            for key, item in value.items()
            if key not in ignored_fields
        }
    if isinstance(value, list):
        return [_drop_ignored_fields(item, ignored_fields) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class SnapshotIdentity:
    """Versioned identity for one reproducible model input snapshot."""

    signal_date: date
    signal_time: SignalTime
    snapshot_version: str
    feature_version: str
    model_version: str
    universe_version: str | None = None
    opportunity_version: str | None = None
    policy_version: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("snapshot_version", "feature_version", "model_version"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_date": self.signal_date.isoformat(),
            "signal_time": self.signal_time.value,
            "snapshot_version": self.snapshot_version,
            "feature_version": self.feature_version,
            "model_version": self.model_version,
            "universe_version": self.universe_version,
            "opportunity_version": self.opportunity_version,
            "policy_version": self.policy_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            signal_date=date.fromisoformat(data["signal_date"]),
            signal_time=SignalTime(data["signal_time"]),
            snapshot_version=data["snapshot_version"],
            feature_version=data["feature_version"],
            model_version=data["model_version"],
            universe_version=data.get("universe_version"),
            opportunity_version=data.get("opportunity_version"),
            policy_version=data.get("policy_version"),
        )
