"""Central pillar versions for MarketLab research outputs."""

from __future__ import annotations

DEFAULT_WORKING_VERSION = "v0.0"
REGIME_VERSION = DEFAULT_WORKING_VERSION
BULLTARD_VERSION = DEFAULT_WORKING_VERSION
POLICY_VERSION = DEFAULT_WORKING_VERSION


def versioned_label(prefix: str, version: str) -> str:
    """Return the conventional label for an algorithm component version."""

    return f"{prefix}_{version}"
