"""Daily OHLCV price observations."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from loguru import logger

DEFAULT_PRICE_OBSERVATIONS_ROOT = Path("data/observations/prices/daily")
HTTP_TIMEOUT_SECONDS = 30.0
STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"


class PriceDataError(ValueError):
    """Raised when price observations cannot be loaded or fetched."""


@dataclass(frozen=True, slots=True)
class DailyPriceObservation:
    """One daily OHLCV price row."""

    source: str
    source_symbol: str
    symbol: str
    observed_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int

    @property
    def dollar_volume(self) -> float:
        return self.close * self.volume

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_symbol": self.source_symbol,
            "symbol": self.symbol,
            "date": self.observed_date.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass(frozen=True, slots=True)
class PriceFetchResult:
    """Result of fetching and writing one symbol's price observations."""

    symbol: str
    source_symbol: str
    observation_path: Path
    row_count: int


def import_daily_price_csv(
    *,
    symbol: str,
    csv_path: Path,
    output_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    source: str = "csv",
    source_symbol: str | None = None,
) -> PriceFetchResult:
    """Import daily OHLCV observations from a local CSV file."""

    normalized_symbol = normalize_symbol(symbol)
    if not csv_path.is_file():
        raise PriceDataError(f"Price CSV path does not exist or is not a file: {csv_path}")
    resolved_source_symbol = source_symbol or normalized_symbol
    rows = parse_stooq_daily_csv(
        csv_path.read_text(encoding="utf-8"),
        symbol=normalized_symbol,
        source_symbol=resolved_source_symbol,
        source=source,
    )
    if not rows:
        raise PriceDataError(f"No daily price rows found in {csv_path}")
    observation_path = write_price_observations(rows, output_root=output_root)
    return PriceFetchResult(
        symbol=normalized_symbol,
        source_symbol=resolved_source_symbol,
        observation_path=observation_path,
        row_count=len(rows),
    )


def fetch_stooq_daily_prices(
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    api_key: str | None = None,
    client: httpx.Client | None = None,
) -> tuple[DailyPriceObservation, ...]:
    """Fetch daily price observations from Stooq's CSV endpoint."""

    normalized_symbol = normalize_symbol(symbol)
    if end_date < start_date:
        raise PriceDataError("End date must be on or after start date")
    source_symbol = to_stooq_symbol(normalized_symbol)
    params = {
        "s": source_symbol,
        "d1": start_date.strftime("%Y%m%d"),
        "d2": end_date.strftime("%Y%m%d"),
        "i": "d",
    }
    if api_key:
        params["apikey"] = api_key
    url = f"{STOOQ_DAILY_URL}?{urlencode(params)}"

    owns_client = client is None
    active_client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=True)
    try:
        logger.bind(
            symbol=normalized_symbol,
            source_symbol=source_symbol,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        ).info("Fetching daily price observations")
        try:
            response = active_client.get(url)
        except httpx.HTTPError as exc:
            raise PriceDataError(f"Failed to fetch prices for {normalized_symbol}: {exc}") from exc
        if response.status_code >= 400:
            raise PriceDataError(
                f"Price fetch for {normalized_symbol} failed with HTTP {response.status_code}; "
                "if Stooq requires an API key, set MARKETLAB_STOOQ_API_KEY "
                "or pass --stooq-api-key"
            )
        rows = parse_stooq_daily_csv(
            response.text,
            symbol=normalized_symbol,
            source_symbol=source_symbol,
        )
        if not rows:
            raise PriceDataError(f"No daily price rows returned for {normalized_symbol}")
        logger.bind(
            symbol=normalized_symbol,
            source_symbol=source_symbol,
            row_count=len(rows),
        ).success("Fetched daily price observations")
        return rows
    finally:
        if owns_client:
            active_client.close()


def fetch_and_write_stooq_daily_prices(
    *,
    symbols: tuple[str, ...],
    start_date: date,
    end_date: date,
    output_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    api_key: str | None = None,
    client: httpx.Client | None = None,
) -> tuple[PriceFetchResult, ...]:
    """Fetch and persist daily price observations for multiple symbols."""

    results: list[PriceFetchResult] = []
    for symbol in dedupe_symbols(symbols):
        rows = fetch_stooq_daily_prices(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            api_key=api_key,
            client=client,
        )
        observation_path = write_price_observations(rows, output_root=output_root)
        results.append(
            PriceFetchResult(
                symbol=rows[0].symbol,
                source_symbol=rows[0].source_symbol,
                observation_path=observation_path,
                row_count=len(rows),
            )
        )
    return tuple(results)


def parse_stooq_daily_csv(
    text: str,
    *,
    symbol: str,
    source_symbol: str,
    source: str = "stooq",
) -> tuple[DailyPriceObservation, ...]:
    """Parse Stooq daily CSV text into price observations."""

    if _looks_like_stooq_error(text):
        raise PriceDataError(_first_nonempty_line(text) or "Stooq returned an error response")

    reader = csv.DictReader(StringIO(text))
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise PriceDataError("Price CSV must include Date, Open, High, Low, Close, Volume columns")

    normalized_symbol = normalize_symbol(symbol)
    rows: list[DailyPriceObservation] = []
    for row_number, row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in row.values()):
            continue
        try:
            rows.append(
                DailyPriceObservation(
                    source=source,
                    source_symbol=source_symbol,
                    symbol=normalized_symbol,
                    observed_date=date.fromisoformat(_required(row, "Date")),
                    open=_parse_float(row, "Open"),
                    high=_parse_float(row, "High"),
                    low=_parse_float(row, "Low"),
                    close=_parse_float(row, "Close"),
                    volume=_parse_int(row, "Volume"),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PriceDataError(f"Invalid price CSV row {row_number}") from exc

    rows.sort(key=lambda price: price.observed_date)
    return tuple(rows)


def write_price_observations(
    rows: tuple[DailyPriceObservation, ...],
    *,
    output_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
) -> Path:
    """Write daily price observations, merging with existing rows by date."""

    if not rows:
        raise PriceDataError("Cannot write an empty price observation set")
    symbol = rows[0].symbol
    if any(row.symbol != symbol for row in rows):
        raise PriceDataError("Price observation set must contain one symbol")

    output_path = output_root / f"{symbol}.jsonl"
    existing_rows = {
        row.observed_date: row for row in load_price_history(symbol=symbol, price_root=output_root)
    }
    merged_rows = dict(existing_rows)
    for row in rows:
        merged_rows[row.observed_date] = row

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(row.to_dict(), sort_keys=True) + "\n"
        for row in sorted(merged_rows.values(), key=lambda price: price.observed_date)
    )
    output_path.write_text(payload, encoding="utf-8")
    logger.bind(
        symbol=symbol,
        row_count=len(rows),
        total_row_count=len(merged_rows),
        observation_path=str(output_path),
    ).success("Wrote daily price observations")
    return output_path


def load_price_history(
    *,
    symbol: str,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
) -> tuple[DailyPriceObservation, ...]:
    """Load one symbol's daily price observations."""

    normalized_symbol = normalize_symbol(symbol)
    path = price_root / f"{normalized_symbol}.jsonl"
    if not path.is_file():
        return ()
    try:
        rows = tuple(
            _price_from_dict(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError as exc:
        raise PriceDataError(f"Failed to read price observations: {path}") from exc
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise PriceDataError(f"Invalid price observations file: {path}") from exc
    return tuple(sorted(rows, key=lambda price: price.observed_date))


def dedupe_symbols(symbols: tuple[str, ...]) -> tuple[str, ...]:
    """Normalize and deduplicate symbols while preserving order."""

    normalized_symbols: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized = normalize_symbol(symbol)
        if normalized not in seen:
            seen.add(normalized)
            normalized_symbols.append(normalized)
    return tuple(normalized_symbols)


def normalize_symbol(symbol: str) -> str:
    """Normalize a public market data symbol."""

    normalized = symbol.strip().upper()
    if not normalized:
        raise PriceDataError("Ticker symbol cannot be empty")
    if any(character.isspace() or character == "/" for character in normalized):
        raise PriceDataError(f"Invalid ticker symbol: {symbol}")
    return normalized


def to_stooq_symbol(symbol: str) -> str:
    """Convert a US equity/ETF symbol to Stooq's default symbol spelling."""

    normalized = normalize_symbol(symbol)
    if normalized.startswith("^") or _has_explicit_stooq_suffix(normalized):
        return normalized.lower()
    return f"{normalized.lower()}.us"


def _has_explicit_stooq_suffix(symbol: str) -> bool:
    if "." not in symbol:
        return False
    suffix = symbol.rsplit(".", 1)[1]
    return suffix.isalpha() and len(suffix) in {2, 3}


def _price_from_dict(row: dict[str, Any]) -> DailyPriceObservation:
    return DailyPriceObservation(
        source=str(row["source"]),
        source_symbol=str(row["source_symbol"]),
        symbol=normalize_symbol(str(row["symbol"])),
        observed_date=date.fromisoformat(str(row["date"])),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=int(row["volume"]),
    )


def _required(row: dict[str, str | None], key: str) -> str:
    value = row[key]
    if value is None or not value.strip():
        raise ValueError(f"Missing {key}")
    return value.strip()


def _parse_float(row: dict[str, str | None], key: str) -> float:
    return float(_required(row, key).replace(",", ""))


def _parse_int(row: dict[str, str | None], key: str) -> int:
    return int(float(_required(row, key).replace(",", "")))


def _looks_like_stooq_error(text: str) -> bool:
    first_line = _first_nonempty_line(text).lower()
    return any(marker in first_line for marker in ("no data", "error", "apikey"))


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""
