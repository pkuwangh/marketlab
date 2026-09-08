from datetime import date
from pathlib import Path

import pytest

from marketlab.snapshots.models import (
    SignalTime,
    SnapshotIdentity,
    resolve_snapshot_path,
    versioned_snapshot_path,
)


def test_snapshot_identity_serializes_versions() -> None:
    identity = SnapshotIdentity(
        signal_date=date(2026, 8, 24),
        signal_time=SignalTime.EOD,
        snapshot_version="2026-08-24_eod",
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


def test_resolve_snapshot_path_requires_artifact_version_when_ambiguous(tmp_path: Path) -> None:
    source_date = date(2026, 8, 24)
    for artifact_version in ("model_v1", "model_v2"):
        path = versioned_snapshot_path(
            snapshot_root=tmp_path,
            source_date=source_date,
            signal_time=SignalTime.EOD,
            snapshot_version=None,
            artifact_version=artifact_version,
            filename="regime.json",
        )
        path.parent.mkdir(parents=True)
        path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="Specify artifact_version explicitly"):
        resolve_snapshot_path(
            snapshot_root=tmp_path,
            source_date=source_date,
            signal_time=SignalTime.EOD,
            filename="regime.json",
            legacy_suffix="-regime.json",
        )

    assert (
        resolve_snapshot_path(
            snapshot_root=tmp_path,
            source_date=source_date,
            signal_time=SignalTime.EOD,
            artifact_version="model_v2",
            filename="regime.json",
            legacy_suffix="-regime.json",
        )
        == tmp_path
        / "2026-08-24"
        / "eod"
        / "2026-08-24_eod"
        / "model_v2"
        / "regime.json"
    )
