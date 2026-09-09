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


def test_snapshot_identity_serializes_versions() -> None:
    identity = SnapshotIdentity(
        signal_date=date(2026, 8, 24),
        signal_time=SignalTime.EOD,
        snapshot_version="v0",
        feature_version="features_v0",
        model_version="regime_v0",
        universe_version="largecap_v0",
        opportunity_version="opportunity_v0",
        policy_version="policy_v0",
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
            feature_version="features_v0",
            model_version="regime_v0",
        )


def test_default_snapshot_version_is_working_v0() -> None:
    assert default_snapshot_version(date(2026, 8, 24), signal_time=SignalTime.EOD) == "v0"


def test_versioned_snapshot_path_uses_date_time_version_file_layout(tmp_path: Path) -> None:
    source_date = date(2026, 8, 24)
    path = versioned_snapshot_path(
        snapshot_root=tmp_path,
        source_date=source_date,
        signal_time=SignalTime.EOD,
        snapshot_version=None,
        filename="regime.json",
    )

    assert path == tmp_path / "2026-08-24" / "eod" / "v0" / "regime.json"


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


def test_write_snapshot_payload_overwrites_different_content_by_default(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.json"

    assert write_snapshot_payload(path=path, payload='{"value": 1}\n') is True
    assert write_snapshot_payload(path=path, payload='{"value": 2}\n') is True
    assert path.read_text(encoding="utf-8") == '{"value": 2}\n'
