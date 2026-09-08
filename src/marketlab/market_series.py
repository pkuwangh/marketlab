"""Scalar market and economic series observations."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from marketlab.snapshots.models import utc_timestamp

DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT = Path("data/observations/market/series")
FRED_GRAPH_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
HTTP_TIMEOUT_SECONDS = 30.0
FRED_CURRENT_VINTAGE_MODE = "current_vintage_backfill"


@dataclass(frozen=True, slots=True)
class FredSeriesSpec:
    """Minimal source metadata for one FRED series."""

    series_id: str
    unit: str
    availability_lag_days: int


FRED_SERIES_SPECS = {
    "BAMLH0A0HYM2": FredSeriesSpec(
        series_id="BAMLH0A0HYM2",
        unit="percent_level",
        availability_lag_days=1,
    ),
    "NFCI": FredSeriesSpec(
        series_id="NFCI",
        unit="index",
        availability_lag_days=5,
    ),
    "DGS10": FredSeriesSpec(
        series_id="DGS10",
        unit="percent_level",
        availability_lag_days=1,
    ),
    "DGS2": FredSeriesSpec(
        series_id="DGS2",
        unit="percent_level",
        availability_lag_days=1,
    ),
}
DEFAULT_FRED_MARKET_SERIES_IDS = tuple(FRED_SERIES_SPECS)


class MarketSeriesError(ValueError):
    """Raised when market series observations cannot be read or written."""


@dataclass(frozen=True, slots=True)
class MarketSeriesObservation:
    """One scalar market or economic series observation."""

    source: str
    source_series_id: str
    series_id: str
    observed_date: date
    availability_date: date
    value: float
    unit: str
    vintage_mode: str = FRED_CURRENT_VINTAGE_MODE
    retrieved_at: str | None = field(default=None, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_series_id": self.source_series_id,
            "series_id": self.series_id,
            "observed_date": self.observed_date.isoformat(),
            "availability_date": self.availability_date.isoformat(),
            "value": self.value,
            "unit": self.unit,
            "vintage_mode": self.vintage_mode,
            "retrieved_at": self.retrieved_at,
        }


@dataclass(frozen=True, slots=True)
class MarketSeriesFetchResult:
    """Result of fetching and writing one scalar market series."""

    series_id: str
    source_series_id: str
    observation_path: Path
    row_count: int
    latest_observed_date: date
    latest_availability_date: date


def fetch_and_write_fred_series(
    *,
    series_ids: tuple[str, ...] = DEFAULT_FRED_MARKET_SERIES_IDS,
    start_date: date,
    end_date: date,
    output_root: Path = DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
    client: httpx.Client | None = None,
) -> tuple[MarketSeriesFetchResult, ...]:
    """Fetch and persist FRED scalar series observations."""

    results: list[MarketSeriesFetchResult] = []
    for series_id in dedupe_series_ids(series_ids):
        rows = fetch_fred_series(
            series_id=series_id,
            start_date=start_date,
            end_date=end_date,
            client=client,
        )
        observation_path = write_market_series_observations(rows, output_root=output_root)
        results.append(
            MarketSeriesFetchResult(
                series_id=rows[0].series_id,
                source_series_id=rows[0].source_series_id,
                observation_path=observation_path,
                row_count=len(rows),
                latest_observed_date=rows[-1].observed_date,
                latest_availability_date=rows[-1].availability_date,
            )
        )
    return tuple(results)


def fetch_fred_series(
    *,
    series_id: str,
    start_date: date,
    end_date: date,
    client: httpx.Client | None = None,
) -> tuple[MarketSeriesObservation, ...]:
    """Fetch one scalar series from FRED's graph CSV endpoint."""

    normalized_series_id = normalize_series_id(series_id)
    if end_date < start_date:
        raise MarketSeriesError("End date must be on or after start date")

    owns_client = client is None
    active_client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=True)
    try:
        logger.bind(
            series_id=normalized_series_id,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        ).info("Fetching FRED market series observations")
        try:
            response = active_client.get(FRED_GRAPH_CSV_URL, params={"id": normalized_series_id})
        except httpx.HTTPError as exc:
            raise MarketSeriesError(
                f"Failed to fetch FRED series {normalized_series_id}: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise MarketSeriesError(
                f"FRED series fetch for {normalized_series_id} failed with "
                f"HTTP {response.status_code}"
            )
        rows = parse_fred_graph_csv(
            response.text,
            series_id=normalized_series_id,
            start_date=start_date,
            end_date=end_date,
        )
        if not rows:
            raise MarketSeriesError(f"No FRED rows returned for {normalized_series_id}")
        retrieved_at = utc_timestamp()
        rows = tuple(replace(row, retrieved_at=retrieved_at) for row in rows)
        logger.bind(
            series_id=normalized_series_id,
            row_count=len(rows),
            latest_observed_date=rows[-1].observed_date.isoformat(),
        ).success("Fetched FRED market series observations")
        return rows
    finally:
        if owns_client:
            active_client.close()


def parse_fred_graph_csv(
    text: str,
    *,
    series_id: str,
    start_date: date,
    end_date: date,
) -> tuple[MarketSeriesObservation, ...]:
    """Parse FRED graph CSV text into scalar observations."""

    normalized_series_id = normalize_series_id(series_id)
    spec = fred_series_spec(normalized_series_id)
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise MarketSeriesError("FRED CSV is empty")
    date_field = _find_date_field(reader.fieldnames)
    value_field = _find_value_field(reader.fieldnames, normalized_series_id, date_field)

    rows: list[MarketSeriesObservation] = []
    for row_number, row in enumerate(reader, start=2):
        try:
            observed_date = date.fromisoformat(_required(row, date_field))
        except (KeyError, ValueError) as exc:
            raise MarketSeriesError(f"Invalid FRED row {row_number}") from exc
        if not start_date <= observed_date <= end_date:
            continue
        value_text = row.get(value_field, "")
        if _is_missing_value(value_text):
            continue
        try:
            value = float(str(value_text).strip())
        except ValueError as exc:
            raise MarketSeriesError(f"Invalid FRED row {row_number}") from exc
        rows.append(
            MarketSeriesObservation(
                source="fred",
                source_series_id=normalized_series_id,
                series_id=normalized_series_id,
                observed_date=observed_date,
                availability_date=observed_date + timedelta(days=spec.availability_lag_days),
                value=value,
                unit=spec.unit,
            )
        )

    rows.sort(key=lambda observation: observation.observed_date)
    return tuple(rows)


def write_market_series_observations(
    rows: tuple[MarketSeriesObservation, ...],
    *,
    output_root: Path = DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
    overwrite: bool = False,
) -> Path:
    """Write scalar market series observations, merging without silent corrections."""

    if not rows:
        raise MarketSeriesError("Cannot write an empty market series observation set")
    series_id = rows[0].series_id
    if any(row.series_id != series_id for row in rows):
        raise MarketSeriesError("Market series observation set must contain one series")

    output_path = output_root / f"{series_id}.jsonl"
    existing_rows = {
        row.observed_date: row
        for row in load_market_series_history(series_id=series_id, observations_root=output_root)
    }
    merged_rows = dict(existing_rows)
    for row in rows:
        existing_row = merged_rows.get(row.observed_date)
        if existing_row is not None and not overwrite:
            if existing_row != row:
                raise MarketSeriesError(
                    "Refusing to overwrite existing market series observation with different "
                    f"content: {output_path} {row.observed_date.isoformat()}"
                )
            continue
        merged_rows[row.observed_date] = row

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(row.to_dict(), sort_keys=True) + "\n"
        for row in sorted(merged_rows.values(), key=lambda observation: observation.observed_date)
    )
    output_path.write_text(payload, encoding="utf-8")
    logger.bind(
        series_id=series_id,
        row_count=len(rows),
        total_row_count=len(merged_rows),
        observation_path=str(output_path),
    ).success("Wrote market series observations")
    return output_path


def load_market_series_history(
    *,
    series_id: str,
    observations_root: Path = DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
) -> tuple[MarketSeriesObservation, ...]:
    """Load one scalar market series observation history."""

    normalized_series_id = normalize_series_id(series_id)
    path = observations_root / f"{normalized_series_id}.jsonl"
    if not path.is_file():
        return ()
    try:
        rows = tuple(
            _observation_from_dict(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError as exc:
        raise MarketSeriesError(f"Failed to read market series observations: {path}") from exc
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise MarketSeriesError(f"Invalid market series observations file: {path}") from exc
    return tuple(sorted(rows, key=lambda observation: observation.observed_date))


def dedupe_series_ids(series_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Normalize and deduplicate FRED-style series IDs while preserving order."""

    normalized_series_ids: list[str] = []
    seen: set[str] = set()
    for series_id in series_ids:
        normalized = normalize_series_id(series_id)
        if normalized not in seen:
            seen.add(normalized)
            normalized_series_ids.append(normalized)
    return tuple(normalized_series_ids)


def normalize_series_id(series_id: str) -> str:
    """Normalize a scalar market series ID."""

    normalized = series_id.strip().upper()
    if not normalized:
        raise MarketSeriesError("Market series ID cannot be empty")
    if any(character.isspace() or character in {"/", ","} for character in normalized):
        raise MarketSeriesError(f"Invalid market series ID: {series_id}")
    return normalized


def fred_series_spec(series_id: str) -> FredSeriesSpec:
    """Return source metadata for a known FRED series."""

    normalized_series_id = normalize_series_id(series_id)
    return FRED_SERIES_SPECS.get(
        normalized_series_id,
        FredSeriesSpec(
            series_id=normalized_series_id,
            unit="number",
            availability_lag_days=1,
        ),
    )


def _observation_from_dict(row: dict[str, Any]) -> MarketSeriesObservation:
    return MarketSeriesObservation(
        source=str(row["source"]),
        source_series_id=str(row["source_series_id"]),
        series_id=normalize_series_id(str(row["series_id"])),
        observed_date=date.fromisoformat(str(row["observed_date"])),
        availability_date=date.fromisoformat(str(row["availability_date"])),
        value=float(row["value"]),
        unit=str(row["unit"]),
        vintage_mode=str(row.get("vintage_mode", FRED_CURRENT_VINTAGE_MODE)),
        retrieved_at=_optional_str(row.get("retrieved_at")),
    )


def _find_date_field(fieldnames: list[str]) -> str:
    for fieldname in fieldnames:
        if fieldname.strip().lower() in {"observation_date", "date"}:
            return fieldname
    raise MarketSeriesError("FRED CSV must include an observation_date column")


def _find_value_field(fieldnames: list[str], series_id: str, date_field: str) -> str:
    for fieldname in fieldnames:
        if fieldname != date_field and fieldname.strip().upper() == series_id:
            return fieldname
    for fieldname in fieldnames:
        if fieldname != date_field:
            return fieldname
    raise MarketSeriesError("FRED CSV must include a value column")


def _required(row: dict[str, str | None], key: str) -> str:
    value = row[key]
    if value is None or not value.strip():
        raise ValueError(f"Missing {key}")
    return value.strip()


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _is_missing_value(value: object) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text == "."
