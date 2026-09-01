"""Point-in-time market signal snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger

from marketlab.snapshots.models import (
    SignalTime,
    current_code_revision,
    default_snapshot_version,
    resolve_snapshot_path,
    signal_time_value,
    utc_timestamp,
    versioned_snapshot_path,
    write_immutable_payload,
)

DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT = Path("data/snapshots/market/signals")
MARKET_SIGNAL_FEATURE_VERSION = "market_signals_v0"
MARKET_SIGNAL_MODEL_VERSION = "market_signals_model_v0"
MARKET_SIGNAL_SNAPSHOT_FILENAME = "market-signals.jsonl"


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
    details: dict[str, Any] = field(default_factory=dict)
    signal_time: str = SignalTime.EOD.value
    snapshot_version: str | None = None
    model_version: str = MARKET_SIGNAL_MODEL_VERSION
    created_at: str | None = field(default=None, compare=False)
    code_revision: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        signal_time = signal_time_value(self.signal_time)
        object.__setattr__(self, "signal_time", signal_time)
        if not self.snapshot_version:
            object.__setattr__(
                self,
                "snapshot_version",
                default_snapshot_version(self.source_date, signal_time=signal_time),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": "marketlab",
            "snapshot_type": "market-signal",
            "source_date": self.source_date.isoformat(),
            "signal_date": self.source_date.isoformat(),
            "signal_time": self.signal_time,
            "snapshot_version": self.snapshot_version,
            "feature_version": self.feature_version,
            "model_version": self.model_version,
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
            "details": self.details,
            "created_at": self.created_at,
            "code_revision": self.code_revision,
        }


def write_market_signal_snapshot(
    signals: tuple[MarketSignal, ...],
    *,
    snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    overwrite: bool = False,
) -> Path:
    """Write one date's market signal rows."""

    if not signals:
        raise MarketSignalError("Cannot write an empty market signal snapshot")
    source_date = signals[0].source_date
    if any(signal.source_date != source_date for signal in signals):
        raise MarketSignalError("Market signal snapshot must contain one source date")
    signal_time = signals[0].signal_time
    if any(signal.signal_time != signal_time for signal in signals):
        raise MarketSignalError("Market signal snapshot must contain one signal time")
    snapshot_version = signals[0].snapshot_version
    if any(signal.snapshot_version != snapshot_version for signal in signals):
        raise MarketSignalError("Market signal snapshot must contain one snapshot version")
    model_version = signals[0].model_version
    if any(signal.model_version != model_version for signal in signals):
        raise MarketSignalError("Market signal snapshot must contain one model version")

    try:
        path = versioned_snapshot_path(
            snapshot_root=snapshot_root,
            source_date=source_date,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
            artifact_version=model_version,
            filename=MARKET_SIGNAL_SNAPSHOT_FILENAME,
        )
    except ValueError as exc:
        raise MarketSignalError(str(exc)) from exc
    created_at = utc_timestamp()
    code_revision = current_code_revision()
    payload = "".join(
        json.dumps(
            _with_write_provenance(
                signal.to_dict(),
                created_at=created_at,
                code_revision=code_revision,
            ),
            sort_keys=True,
        )
        + "\n"
        for signal in signals
    )
    wrote = write_immutable_payload(
        path=path,
        payload=payload,
        error_cls=MarketSignalError,
        overwrite=overwrite,
    )
    logger.bind(
        source_date=source_date.isoformat(),
        row_count=len(signals),
        snapshot_path=str(path),
        wrote=wrote,
    ).success("Wrote market signal snapshot")
    return path


def load_market_signal_snapshot(
    *,
    source_date: date,
    snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
    model_version: str | None = None,
) -> tuple[MarketSignal, ...]:
    """Load one date's market signal rows."""

    try:
        path = resolve_snapshot_path(
            snapshot_root=snapshot_root,
            source_date=source_date,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
            artifact_version=model_version,
            filename=MARKET_SIGNAL_SNAPSHOT_FILENAME,
            legacy_suffix=".jsonl",
        )
    except ValueError as exc:
        raise MarketSignalError(str(exc)) from exc
    if path is None:
        return ()
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
    source_date = date.fromisoformat(str(row["source_date"]))
    signal_time = str(row.get("signal_time", SignalTime.EOD.value))
    return MarketSignal(
        source_date=source_date,
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
        details=_optional_details(row.get("details")),
        signal_time=signal_time,
        snapshot_version=_optional_str(row.get("snapshot_version"))
        or default_snapshot_version(source_date, signal_time=signal_time),
        model_version=_optional_str(row.get("model_version")) or MARKET_SIGNAL_MODEL_VERSION,
        created_at=_optional_str(row.get("created_at")),
        code_revision=_optional_str(row.get("code_revision")),
    )


def _optional_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    return date.fromisoformat(str(value))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_details(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MarketSignalError("Market signal details must be an object")
    return dict(value)


def _with_write_provenance(
    row: dict[str, Any],
    *,
    created_at: str,
    code_revision: str | None,
) -> dict[str, Any]:
    enriched = dict(row)
    if enriched.get("created_at") is None:
        enriched["created_at"] = created_at
    if enriched.get("code_revision") is None:
        enriched["code_revision"] = code_revision
    return enriched


def _format_score(value: int) -> str:
    return f"{value:+d}"


def _format_value(value: float | str | None, unit: str) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if unit == "percent":
            return f"{value * 100:+.1f}%"
        if unit == "percent_level":
            return f"{value:.2f}%"
        if unit == "percentage_points":
            return f"{value:+.2f}pp"
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
