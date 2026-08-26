"""Small Bulltard ingestion contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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


class RankedTradeSide(StrEnum):
    """Directional side for a ranked Bulltard ticker row."""

    BULLISH = "bullish"
    BEARISH = "bearish"


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


@dataclass(frozen=True, slots=True)
class RankedOptionTradeObservation:
    """One ticker row from the Bulltard ranked option trades view."""

    source_date: date
    view: BulltardView
    side: RankedTradeSide
    symbol: str
    trade_count: int
    last_trade_date: date
    avg_dte: float | None
    score: float
    premium: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": "bulltard",
            "source_date": self.source_date.isoformat(),
            "view": self.view.value,
            "side": self.side.value,
            "symbol": self.symbol,
            "trade_count": self.trade_count,
            "last_trade_date": self.last_trade_date.isoformat(),
            "avg_dte": self.avg_dte,
            "score": self.score,
            "premium": self.premium,
        }


@dataclass(frozen=True, slots=True)
class TickerFlowObservation:
    """One option-flow row from a Bulltard ticker detail page."""

    source_date: date
    symbol: str
    traded_at: datetime
    order_type: str
    side: RankedTradeSide | None
    contract: str
    contract_type: str | None
    expiry: date
    contracts: int
    premium: float | None
    is_older: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": "bulltard",
            "source_date": self.source_date.isoformat(),
            "view": "ticker-flow-history",
            "symbol": self.symbol,
            "traded_at": self.traded_at.isoformat(timespec="minutes"),
            "order_type": self.order_type,
            "side": self.side.value if self.side else None,
            "contract": self.contract,
            "contract_type": self.contract_type,
            "expiry": self.expiry.isoformat(),
            "contracts": self.contracts,
            "premium": self.premium,
            "is_older": self.is_older,
        }


@dataclass(frozen=True, slots=True)
class TradeOfInterestObservation:
    """One ticker note from the recap's Trades Of Interest section."""

    source_date: date
    rank: int
    symbol: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": "bulltard",
            "source_date": self.source_date.isoformat(),
            "view": "trades-of-interest",
            "rank": self.rank,
            "symbol": self.symbol,
            "note": self.note,
        }
