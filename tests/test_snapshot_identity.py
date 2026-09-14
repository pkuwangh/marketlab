from datetime import date
from pathlib import Path

import pytest

from marketlab.snapshots.models import (
    SignalTime,
    SnapshotIdentity,
    default_snapshot_version,
    resolve_snapshot_path,
    versioned_snapshot_path,
    write_snapshot_payload,
)
from marketlab.versions import (
    BULLTARD_SNAPSHOT_VERSION,
    BULLTARD_VERSION,
    POLICY_SNAPSHOT_VERSION,
    POLICY_VERSION,
    REGIME_SNAPSHOT_VERSION,
    REGIME_VERSION,
)


def test_snapshot_identity_serializes_versions() -> None:
    identity = SnapshotIdentity(
        signal_date=date(2026, 8, 24),
        signal_time=SignalTime.EOD,
        snapshot_version="v0.0",
        feature_version="features_v0.0",
        model_version="regime_v0.0",
        universe_version="largecap_v0.0",
        opportunity_version="opportunity_v0.0",
        policy_version="policy_v0.0",
    )

    data = identity.to_dict()

    assert data["signal_date"] == "2026-08-24"
    assert data["signal_time"] == "eod"
    assert SnapshotIdentity.from_dict(data) == identity


def test_snapshot_identity_requires_core_versions() -> None:
    with pytest.raises(ValueError, match="snapshot_version is required"):
        SnapshotIdentity(
            signal_date=date(2026, 8, 24),
            signal_time=SignalTime.EOD,
            snapshot_version="",
            feature_version="features_v0.0",
            model_version="regime_v0.0",
        )


def test_default_snapshot_version_is_current_regime_version() -> None:
    assert (
        default_snapshot_version(date(2026, 8, 24), signal_time=SignalTime.EOD)
        == REGIME_SNAPSHOT_VERSION
    )


def test_pillar_snapshot_versions_track_pillar_versions() -> None:
    assert REGIME_SNAPSHOT_VERSION == REGIME_VERSION
    assert BULLTARD_SNAPSHOT_VERSION == BULLTARD_VERSION
    assert POLICY_SNAPSHOT_VERSION == POLICY_VERSION


def test_default_snapshot_version_accepts_caller_default() -> None:
    assert (
        default_snapshot_version(
            date(2026, 8, 24),
            signal_time=SignalTime.EOD,
            default_version="v9.9",
        )
        == "v9.9"
    )


def test_versioned_snapshot_path_uses_date_time_version_file_layout(tmp_path: Path) -> None:
    source_date = date(2026, 8, 24)
    path = versioned_snapshot_path(
        snapshot_root=tmp_path,
        source_date=source_date,
        signal_time=SignalTime.EOD,
        snapshot_version=None,
        filename="regime.json",
    )

    assert path == tmp_path / "2026-08-24" / "eod" / REGIME_SNAPSHOT_VERSION / "regime.json"


def test_versioned_snapshot_path_uses_caller_default_version(tmp_path: Path) -> None:
    source_date = date(2026, 8, 24)
    path = versioned_snapshot_path(
        snapshot_root=tmp_path,
        source_date=source_date,
        signal_time=SignalTime.EOD,
        snapshot_version=None,
        filename="regime.json",
        default_version="v9.9",
    )

    assert path == tmp_path / "2026-08-24" / "eod" / "v9.9" / "regime.json"


def test_resolve_snapshot_path_returns_same_version_snapshot(tmp_path: Path) -> None:
    source_date = date(2026, 8, 24)
    path = versioned_snapshot_path(
        snapshot_root=tmp_path,
        source_date=source_date,
        signal_time=SignalTime.EOD,
        snapshot_version=None,
        filename="regime.json",
    )
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")

    assert (
        resolve_snapshot_path(
            snapshot_root=tmp_path,
            source_date=source_date,
            signal_time=SignalTime.EOD,
            filename="regime.json",
            legacy_suffix="-regime.json",
        )
        == path
    )


def test_resolve_snapshot_path_uses_caller_default_version(tmp_path: Path) -> None:
    source_date = date(2026, 8, 24)
    path = versioned_snapshot_path(
        snapshot_root=tmp_path,
        source_date=source_date,
        signal_time=SignalTime.EOD,
        snapshot_version=None,
        filename="regime.json",
        default_version="v9.9",
    )
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")

    assert (
        resolve_snapshot_path(
            snapshot_root=tmp_path,
            source_date=source_date,
            signal_time=SignalTime.EOD,
            filename="regime.json",
            legacy_suffix="-regime.json",
            default_version="v9.9",
        )
        == path
    )


def test_resolve_snapshot_path_preserves_legacy_fallback_with_caller_default(
    tmp_path: Path,
) -> None:
    source_date = date(2026, 8, 24)
    legacy_path = tmp_path / "2026-08-24-regime.json"
    legacy_path.write_text("{}", encoding="utf-8")

    assert (
        resolve_snapshot_path(
            snapshot_root=tmp_path,
            source_date=source_date,
            signal_time=SignalTime.EOD,
            filename="regime.json",
            legacy_suffix="-regime.json",
            default_version="v9.9",
        )
        == legacy_path
    )


def test_write_snapshot_payload_overwrites_different_content_by_default(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.json"

    assert write_snapshot_payload(path=path, payload='{"value": 1}\n') is True
    assert write_snapshot_payload(path=path, payload='{"value": 2}\n') is True
    assert path.read_text(encoding="utf-8") == '{"value": 2}\n'
