from datetime import date

import pytest

from marketlab.snapshots.models import SignalTime, SnapshotIdentity


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
