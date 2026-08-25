"""Point-in-time snapshot identifiers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Self


class SignalTime(StrEnum):
    """Canonical time modes for official and provisional research signals."""

    PRIOR_CLOSE = "prior_close"
    INTRADAY_PREVIEW = "intraday_preview"
    EOD = "eod"


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
