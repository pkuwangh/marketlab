"""Small Bulltard ingestion contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any


class BulltardView(StrEnum):
    """Bulltard views supported by the current ingest path."""

    RANKED_OPTION_TRADES = "ranked-option-trades"

    @property
    def route_path(self) -> str:
        match self:
            case BulltardView.RANKED_OPTION_TRADES:
                return "/ranked_option_trades"

    @property
    def output_slug(self) -> str:
        return self.value.replace("-", "_")


@dataclass(frozen=True, slots=True)
class IngestPlan:
    """Resolved inputs for one targeted Bulltard ingest run."""

    source_date: date
    view: BulltardView
    recap_path: Path
    signed_url: str
    observation_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": "bulltard",
            "source_date": self.source_date.isoformat(),
            "view": self.view.value,
            "recap_path": str(self.recap_path),
            "signed_url": self.signed_url,
            "observation_path": str(self.observation_path),
        }
