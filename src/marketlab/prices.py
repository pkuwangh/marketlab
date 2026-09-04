"""Daily OHLCV price observations."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from loguru import logger

from marketlab.snapshots.models import utc_timestamp

DEFAULT_PRICE_OBSERVATIONS_ROOT = Path("data/observations/prices/daily")
HTTP_TIMEOUT_SECONDS = 30.0
STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"
YAHOO_REQUIRED_PRICE_COLUMNS = (
    ("Open", "open"),
    ("High", "high"),
    ("Low", "low"),
    ("Close", "close"),
    ("Volume", "volume"),
)


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
    adjusted_close: float | None = None
    availability_date: date | None = None
    retrieved_at: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.availability_date is None:
            object.__setattr__(self, "availability_date", self.observed_date)

    @property
    def dollar_volume(self) -> float:
        return self.close * self.volume

    @property
    def return_close(self) -> float:
        return self.adjusted_close if self.adjusted_close is not None else self.close

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
            "adjusted_close": self.adjusted_close,
            "availability_date": self.availability_date.isoformat()
            if self.availability_date
            else None,
            "retrieved_at": self.retrieved_at,
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
        retrieved_at = utc_timestamp()
        rows = tuple(replace(row, retrieved_at=retrieved_at) for row in rows)
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
        observation_path = write_price_observations(
            rows,
            output_root=output_root,
            overwrite=True,
        )
        results.append(
            PriceFetchResult(
                symbol=rows[0].symbol,
                source_symbol=rows[0].source_symbol,
                observation_path=observation_path,
                row_count=len(rows),
            )
        )
    return tuple(results)


def fetch_yahoo_daily_prices(
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    downloader=None,
) -> tuple[DailyPriceObservation, ...]:
    """Fetch daily price observations through yfinance."""

    normalized_symbol = normalize_symbol(symbol)
    if end_date < start_date:
        raise PriceDataError("End date must be on or after start date")

    active_downloader = downloader
    if active_downloader is None:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise PriceDataError("yfinance is not installed; run `uv add yfinance`") from exc
        active_downloader = yf.download

    logger.bind(
        symbol=normalized_symbol,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    ).info("Fetching Yahoo daily price observations")
    try:
        frame = active_downloader(
            normalized_symbol,
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=False,
            progress=False,
            threads=False,
            group_by="column",
            multi_level_index=False,
        )
    except Exception as exc:
        raise PriceDataError(
            f"Failed to fetch Yahoo prices for {normalized_symbol}: {exc}"
        ) from exc

    rows = parse_yahoo_daily_frame(
        frame,
        symbol=normalized_symbol,
        start_date=start_date,
        end_date=end_date,
    )
    if not rows:
        raise PriceDataError(f"No Yahoo daily price rows returned for {normalized_symbol}")
    retrieved_at = utc_timestamp()
    rows = tuple(replace(row, retrieved_at=retrieved_at) for row in rows)
    logger.bind(
        symbol=normalized_symbol,
        row_count=len(rows),
        latest_price_date=rows[-1].observed_date.isoformat(),
    ).success("Fetched Yahoo daily price observations")
    return rows


def fetch_and_write_yahoo_daily_prices(
    *,
    symbols: tuple[str, ...],
    start_date: date,
    end_date: date,
    output_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    downloader=None,
) -> tuple[PriceFetchResult, ...]:
    """Fetch and persist Yahoo daily price observations for multiple symbols."""

    results: list[PriceFetchResult] = []
    for symbol in dedupe_symbols(symbols):
        rows = fetch_yahoo_daily_prices(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            downloader=downloader,
        )
        observation_path = write_price_observations(
            rows,
            output_root=output_root,
            overwrite=True,
        )
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
                    adjusted_close=_parse_optional_float(row, "Adj Close"),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PriceDataError(f"Invalid price CSV row {row_number}") from exc

    rows.sort(key=lambda price: price.observed_date)
    return tuple(rows)


def parse_yahoo_daily_frame(
    frame,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
) -> tuple[DailyPriceObservation, ...]:
    """Parse a yfinance daily price frame into price observations."""

    normalized_symbol = normalize_symbol(symbol)
    if frame is None or getattr(frame, "empty", False):
        return ()
    try:
        records = frame.reset_index().to_dict("records")
    except AttributeError as exc:
        raise PriceDataError("Yahoo price result must be a pandas-like DataFrame") from exc

    filtered_records: list[tuple[int, dict[Any, Any], date]] = []
    for row_number, row in enumerate(records, start=1):
        observed_date = _coerce_observed_date(_frame_value(row, "Date", "Datetime", "index"))
        if observed_date is None or not start_date <= observed_date <= end_date:
            continue
        filtered_records.append((row_number, row, observed_date))

    last_complete_index = max(
        (
            index
            for index, (_row_number, row, _observed_date) in enumerate(filtered_records)
            if not _missing_required_yahoo_price_fields(row)
        ),
        default=-1,
    )

    rows: list[DailyPriceObservation] = []
    for index, (row_number, row, observed_date) in enumerate(filtered_records):
        missing_fields = _missing_required_yahoo_price_fields(row)
        if missing_fields:
            if index > last_complete_index:
                logger.bind(
                    symbol=normalized_symbol,
                    row_number=row_number,
                    observed_date=observed_date.isoformat(),
                    missing_fields=missing_fields,
                ).debug("Skipping incomplete trailing Yahoo daily price row")
                continue
            raise PriceDataError(f"Invalid Yahoo price row {row_number}")
        try:
            rows.append(
                DailyPriceObservation(
                    source="yahoo",
                    source_symbol=normalized_symbol,
                    symbol=normalized_symbol,
                    observed_date=observed_date,
                    open=_frame_float(row, "Open", "open"),
                    high=_frame_float(row, "High", "high"),
                    low=_frame_float(row, "Low", "low"),
                    close=_frame_float(row, "Close", "close"),
                    volume=_frame_int(row, "Volume", "volume"),
                    adjusted_close=_frame_optional_float(
                        row,
                        "Adj Close",
                        "AdjClose",
                        "adj close",
                        "adjclose",
                    ),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PriceDataError(f"Invalid Yahoo price row {row_number}") from exc
    rows.sort(key=lambda price: price.observed_date)
    return tuple(rows)


def write_price_observations(
    rows: tuple[DailyPriceObservation, ...],
    *,
    output_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    overwrite: bool = False,
) -> Path:
    """Write daily price observations, merging by date."""

    if not rows:
        raise PriceDataError("Cannot write an empty price observation set")
    symbol = rows[0].symbol
    if any(row.symbol != symbol for row in rows):
        raise PriceDataError("Price observation set must contain one symbol")

    output_path = price_observation_path(symbol=symbol, price_root=output_root)
    existing_rows = {
        row.observed_date: row for row in load_price_history(symbol=symbol, price_root=output_root)
    }
    merged_rows = dict(existing_rows)
    for row in rows:
        existing_row = merged_rows.get(row.observed_date)
        if existing_row is not None and not overwrite:
            if existing_row != row:
                raise PriceDataError(
                    "Refusing to overwrite existing daily price observation with different "
                    f"content: {output_path} {row.observed_date.isoformat()}"
                )
            continue
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
    paths = _price_observation_read_paths(symbol=normalized_symbol, price_root=price_root)
    existing_paths = tuple(path for path in paths if path.is_file())
    if not existing_paths:
        return ()
    try:
        rows_by_date = {}
        for path in existing_paths:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = _price_from_dict(json.loads(line))
                    rows_by_date[row.observed_date] = row
    except OSError as exc:
        raise PriceDataError(f"Failed to read price observations: {path}") from exc
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise PriceDataError(f"Invalid price observations file: {path}") from exc
    return tuple(sorted(rows_by_date.values(), key=lambda price: price.observed_date))


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


def price_observation_path(*, symbol: str, price_root: Path) -> Path:
    """Return the canonical daily price observation file path for one symbol."""

    return price_root / f"{price_observation_stem(symbol)}.jsonl"


def price_observation_stem(symbol: str) -> str:
    """Return a filesystem-safe price observation stem while preserving stored symbols."""

    normalized = normalize_symbol(symbol)
    if normalized.startswith("^"):
        stripped = normalized[1:]
        if not stripped:
            raise PriceDataError(f"Invalid ticker symbol: {symbol}")
        return f"INDEX_{stripped}"
    return normalized


def _price_observation_read_paths(*, symbol: str, price_root: Path) -> tuple[Path, ...]:
    normalized = normalize_symbol(symbol)
    canonical_path = price_observation_path(symbol=normalized, price_root=price_root)
    legacy_path = price_root / f"{normalized}.jsonl"
    if legacy_path == canonical_path:
        return (canonical_path,)
    return (legacy_path, canonical_path)


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
        adjusted_close=_optional_float(row.get("adjusted_close")),
        availability_date=_optional_date(row.get("availability_date"))
        or date.fromisoformat(str(row["date"])),
        retrieved_at=_optional_str(row.get("retrieved_at")),
    )


def _required(row: dict[str, str | None], key: str) -> str:
    value = row[key]
    if value is None or not value.strip():
        raise ValueError(f"Missing {key}")
    return value.strip()


def _parse_float(row: dict[str, str | None], key: str) -> float:
    return float(_required(row, key).replace(",", ""))


def _parse_optional_float(row: dict[str, str | None], key: str) -> float | None:
    value = row.get(key)
    if value is None or not value.strip():
        return None
    return float(value.replace(",", ""))


def _parse_int(row: dict[str, str | None], key: str) -> int:
    return int(float(_required(row, key).replace(",", "")))


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    return date.fromisoformat(str(value))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _frame_value(row: dict[Any, Any], *names: str) -> Any:
    for name in names:
        if name in row and not _is_missing(row[name]):
            return row[name]
    raise KeyError(names[0])


def _missing_required_yahoo_price_fields(row: dict[Any, Any]) -> tuple[str, ...]:
    missing_fields: list[str] = []
    for names in YAHOO_REQUIRED_PRICE_COLUMNS:
        if not any(name in row and not _is_missing(row[name]) for name in names):
            missing_fields.append(names[0])
    return tuple(missing_fields)


def _frame_float(row: dict[Any, Any], *names: str) -> float:
    value = _frame_value(row, *names)
    if _is_missing(value):
        raise ValueError(names[0])
    return float(value)


def _frame_optional_float(row: dict[Any, Any], *names: str) -> float | None:
    for name in names:
        if name in row and not _is_missing(row[name]):
            return float(row[name])
    return None


def _frame_int(row: dict[Any, Any], *names: str) -> int:
    value = _frame_value(row, *names)
    if _is_missing(value):
        raise ValueError(names[0])
    return int(float(value))


def _coerce_observed_date(value: object) -> date | None:
    if _is_missing(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        coerced = value.date()
        if isinstance(coerced, date):
            return coerced
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError(f"Invalid date value: {value}")


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(math.isnan(value))
    except TypeError:
        return False


def _looks_like_stooq_error(text: str) -> bool:
    first_line = _first_nonempty_line(text).lower()
    return any(marker in first_line for marker in ("no data", "error", "apikey"))


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""
