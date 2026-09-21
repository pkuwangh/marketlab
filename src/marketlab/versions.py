"""Central pillar versions for MarketLab research outputs."""

from __future__ import annotations

REGIME_VERSION = "v1.1"
BULLTARD_VERSION = "v0.0"
POLICY_VERSION = "v0.1"
DEFAULT_WORKING_VERSION = REGIME_VERSION

REGIME_SNAPSHOT_VERSION = REGIME_VERSION
BULLTARD_SNAPSHOT_VERSION = BULLTARD_VERSION
POLICY_SNAPSHOT_VERSION = POLICY_VERSION


def versioned_label(prefix: str, version: str) -> str:
    """Return the conventional label for an algorithm component version."""

    return f"{prefix}_{version}"
