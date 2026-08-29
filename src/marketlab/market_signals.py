"""Point-in-time market signal snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger

DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT = Path("data/snapshots/market/signals")
MARKET_SIGNAL_FEATURE_VERSION = "market_signals_v0"


class MarketSignalError(ValueError):
    """Raised when market signal snapshots cannot be read or written."""


@dataclass(frozen=True, slots=True)
class MarketSignal:
    """One point-in-time market signal row."""

    source_date: date
    feature_version: str
    family: str
    name: str
    status: str
    score: int
    value: float | str | None
    unit: str
    source: str
    observed_date: date | None
    availability_date: date | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": "marketlab",
            "snapshot_type": "market-signal",
            "source_date": self.source_date.isoformat(),
            "feature_version": self.feature_version,
            "family": self.family,
            "name": self.name,
            "status": self.status,
            "score": self.score,
            "value": self.value,
            "unit": self.unit,
            "data_source": self.source,
            "observed_date": self.observed_date.isoformat() if self.observed_date else None,
            "availability_date": (
                self.availability_date.isoformat() if self.availability_date else None
            ),
            "reason": self.reason,
        }


def write_market_signal_snapshot(
    signals: tuple[MarketSignal, ...],
    *,
    snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
) -> Path:
    """Write one date's market signal rows."""

    if not signals:
        raise MarketSignalError("Cannot write an empty market signal snapshot")
    source_date = signals[0].source_date
    if any(signal.source_date != source_date for signal in signals):
        raise MarketSignalError("Market signal snapshot must contain one source date")

    path = snapshot_root / f"{source_date.isoformat()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(signal.to_dict(), sort_keys=True) + "\n" for signal in signals)
    path.write_text(payload, encoding="utf-8")
    logger.bind(
        source_date=source_date.isoformat(),
        row_count=len(signals),
        snapshot_path=str(path),
    ).success("Wrote market signal snapshot")
    return path


def load_market_signal_snapshot(
    *,
    source_date: date,
    snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
) -> tuple[MarketSignal, ...]:
    """Load one date's market signal rows."""

    path = snapshot_root / f"{source_date.isoformat()}.jsonl"
    if not path.is_file():
        return ()
    try:
        return tuple(
            _signal_from_dict(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError as exc:
        raise MarketSignalError(f"Failed to read market signal snapshot: {path}") from exc
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise MarketSignalError(f"Invalid market signal snapshot file: {path}") from exc


def format_market_signals(signals: tuple[MarketSignal, ...]) -> str:
    """Format market signal rows as a compact table."""

    if not signals:
        return "No market signal rows found."

    rows = [["family", "signal", "score", "status", "value", "source", "observed", "reason"]]
    for signal in signals:
        rows.append(
            [
                signal.family,
                signal.name,
                _format_score(signal.score),
                signal.status,
                _format_value(signal.value, signal.unit),
                signal.source,
                signal.observed_date.isoformat() if signal.observed_date else "-",
                signal.reason,
            ]
        )
    return _format_table(rows)


def _signal_from_dict(row: dict[str, Any]) -> MarketSignal:
    return MarketSignal(
        source_date=date.fromisoformat(str(row["source_date"])),
        feature_version=str(row["feature_version"]),
        family=str(row["family"]),
        name=str(row["name"]),
        status=str(row["status"]),
        score=int(row["score"]),
        value=row.get("value"),
        unit=str(row["unit"]),
        source=str(row["data_source"]),
        observed_date=_optional_date(row.get("observed_date")),
        availability_date=_optional_date(row.get("availability_date")),
        reason=str(row["reason"]),
    )


def _optional_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    return date.fromisoformat(str(value))


def _format_score(value: int) -> str:
    return f"{value:+d}"


def _format_value(value: float | str | None, unit: str) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if unit == "percent":
            return f"{value * 100:+.1f}%"
        if unit in {"index", "ratio"}:
            return f"{value:.2f}"
        return f"{value:.4g}"
    return str(value)


def _format_table(rows: list[list[str]]) -> str:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    lines = []
    for row_index, row in enumerate(rows):
        lines.append("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)
