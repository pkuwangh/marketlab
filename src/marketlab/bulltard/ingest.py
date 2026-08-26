"""Prepare targeted Bulltard ingestion runs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from loguru import logger

from marketlab.bulltard.models import BulltardView, IngestPlan
from marketlab.bulltard.parsers import (
    ParserError,
    parse_ranked_option_trades,
    parse_ticker_flow_history,
)
from marketlab.bulltard.recaps import (
    SignedSourceUrlError,
    extract_signed_source_url,
    extract_trades_of_interest,
)

DEFAULT_OBSERVATIONS_ROOT = Path("data/observations/bulltard")
DEFAULT_DEBUG_ROOT = Path("data/debug/bulltard")
APP_HOST = "app.jamesbulltard.com"
APP_ORIGIN = f"https://{APP_HOST}"
HTTP_TIMEOUT_SECONDS = 30.0
_DATE_IN_NAME_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,15}$")


class IngestError(ValueError):
    """Raised when a Bulltard ingest run cannot be prepared."""


@dataclass(frozen=True, slots=True)
class FetchedView:
    """One retrieved Bulltard view saved for parser bring-up."""

    plan: IngestPlan
    final_url: str
    status_code: int
    content_type: str | None
    byte_count: int
    debug_path: Path


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Result of one targeted Bulltard ingest run."""

    fetched_view: FetchedView
    row_count: int
    observation_path: Path


@dataclass(frozen=True, slots=True)
class FetchedTickerPage:
    """One retrieved Bulltard ticker detail page."""

    source_date: date
    symbol: str
    signed_url: str
    final_url: str
    status_code: int
    content_type: str | None
    byte_count: int
    debug_path: Path


@dataclass(frozen=True, slots=True)
class TickerIngestResult:
    """Result of one targeted Bulltard ticker ingest run."""

    fetched_page: FetchedTickerPage
    row_count: int
    observation_path: Path


@dataclass(frozen=True, slots=True)
class TradesOfInterestIngestResult:
    """Result of parsing Trades Of Interest from one recap."""

    source_date: date
    recap_path: Path
    row_count: int
    observation_path: Path
    symbols: tuple[str, ...]


def build_ingest_plan(
    *,
    source_date: date,
    view: BulltardView,
    recap_path: Path,
    output_root: Path = DEFAULT_OBSERVATIONS_ROOT,
) -> IngestPlan:
    """Resolve the minimal inputs for a targeted Bulltard ingest run."""

    if not recap_path.is_file():
        raise IngestError(f"Recap path does not exist or is not a file: {recap_path}")
    _warn_if_path_date_differs(source_date=source_date, path=recap_path)

    logger.bind(
        source_date=source_date.isoformat(),
        view=view.value,
        recap_path=str(recap_path),
    ).info("Preparing Bulltard ingest")

    try:
        signed_url = extract_signed_source_url(recap_path.read_text(encoding="utf-8"))
    except SignedSourceUrlError as exc:
        raise IngestError(str(exc)) from exc

    observation_path = output_root / view.output_slug / f"{source_date.isoformat()}.jsonl"
    plan = IngestPlan(
        source_date=source_date,
        view=view,
        recap_path=recap_path,
        signed_url=signed_url,
        observation_path=observation_path,
    )
    logger.bind(
        source_date=source_date.isoformat(),
        view=view.value,
        route_path=view.route_path,
        observation_path=str(observation_path),
    ).success("Prepared Bulltard ingest plan")
    return plan


def fetch_ingest_view(
    plan: IngestPlan,
    *,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
    client: httpx.Client | None = None,
) -> FetchedView:
    """Retrieve the planned Bulltard view and save its HTML for parser bring-up."""

    owns_client = client is None
    active_client = client or httpx.Client(
        follow_redirects=True,
        timeout=HTTP_TIMEOUT_SECONDS,
    )

    try:
        logger.bind(
            source_date=plan.source_date.isoformat(),
            view=plan.view.value,
            signed_url=plan.signed_url,
        ).info("Bootstrapping Bulltard access")
        bootstrap = _get(active_client, plan.signed_url, purpose="bootstrap access")
        _require_app_access(bootstrap)

        view_url = f"{APP_ORIGIN}{plan.view.route_path}"
        logger.bind(
            source_date=plan.source_date.isoformat(),
            view=plan.view.value,
            url=view_url,
        ).info("Retrieving Bulltard view")
        response = _get(active_client, view_url, purpose=f"{plan.view.value} view")
        _require_usable_response(response, label=f"{plan.view.value} view")

        debug_path = debug_root / plan.view.output_slug / f"{plan.source_date.isoformat()}.html"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_bytes(response.content)

        result = FetchedView(
            plan=plan,
            final_url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            byte_count=len(response.content),
            debug_path=debug_path,
        )
        logger.bind(
            source_date=plan.source_date.isoformat(),
            view=plan.view.value,
            final_url=result.final_url,
            status_code=result.status_code,
            byte_count=result.byte_count,
            debug_path=str(result.debug_path),
        ).success("Retrieved Bulltard view")
        return result
    finally:
        if owns_client:
            active_client.close()


def ingest_planned_view(
    plan: IngestPlan,
    *,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
    client: httpx.Client | None = None,
) -> IngestResult:
    """Fetch, parse, and write observations for one planned Bulltard view."""

    fetched_view = fetch_ingest_view(plan, debug_root=debug_root, client=client)
    rows = _parse_fetched_view(fetched_view)
    fetched_view.plan.observation_path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row.to_dict(), sort_keys=True) + "\n" for row in rows)
    fetched_view.plan.observation_path.write_text(payload, encoding="utf-8")

    logger.bind(
        source_date=plan.source_date.isoformat(),
        view=plan.view.value,
        row_count=len(rows),
        observation_path=str(plan.observation_path),
    ).success("Wrote Bulltard observations")
    return IngestResult(
        fetched_view=fetched_view,
        row_count=len(rows),
        observation_path=plan.observation_path,
    )


def fetch_ticker_page(
    *,
    source_date: date,
    symbol: str,
    recap_path: Path,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
    client: httpx.Client | None = None,
) -> FetchedTickerPage:
    """Retrieve one Bulltard ticker detail page through the recap access link."""

    if not recap_path.is_file():
        raise IngestError(f"Recap path does not exist or is not a file: {recap_path}")
    _warn_if_path_date_differs(source_date=source_date, path=recap_path)
    normalized_symbol = normalize_ticker_symbol(symbol)

    try:
        signed_url = extract_signed_source_url(recap_path.read_text(encoding="utf-8"))
    except SignedSourceUrlError as exc:
        raise IngestError(str(exc)) from exc

    owns_client = client is None
    active_client = client or httpx.Client(
        follow_redirects=True,
        timeout=HTTP_TIMEOUT_SECONDS,
    )

    try:
        logger.bind(
            source_date=source_date.isoformat(),
            symbol=normalized_symbol,
            signed_url=signed_url,
        ).info("Bootstrapping Bulltard ticker access")
        bootstrap = _get(active_client, signed_url, purpose="bootstrap access")
        _require_app_access(bootstrap)

        ticker_url = f"{APP_ORIGIN}/tickers/{quote(normalized_symbol, safe='.-')}"
        logger.bind(
            source_date=source_date.isoformat(),
            symbol=normalized_symbol,
            url=ticker_url,
        ).info("Retrieving Bulltard ticker page")
        response = _get(active_client, ticker_url, purpose=f"{normalized_symbol} ticker page")
        _require_usable_response(response, label=f"{normalized_symbol} ticker page")

        debug_path = debug_root / "tickers" / normalized_symbol / f"{source_date.isoformat()}.html"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_bytes(response.content)

        result = FetchedTickerPage(
            source_date=source_date,
            symbol=normalized_symbol,
            signed_url=signed_url,
            final_url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            byte_count=len(response.content),
            debug_path=debug_path,
        )
        logger.bind(
            source_date=source_date.isoformat(),
            symbol=normalized_symbol,
            final_url=result.final_url,
            status_code=result.status_code,
            byte_count=result.byte_count,
            debug_path=str(result.debug_path),
        ).success("Retrieved Bulltard ticker page")
        return result
    finally:
        if owns_client:
            active_client.close()


def ingest_ticker_page(
    *,
    source_date: date,
    symbol: str,
    recap_path: Path,
    output_root: Path = DEFAULT_OBSERVATIONS_ROOT,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
    client: httpx.Client | None = None,
) -> TickerIngestResult:
    """Fetch, parse, and write option-flow observations for one Bulltard ticker."""

    fetched_page = fetch_ticker_page(
        source_date=source_date,
        symbol=symbol,
        recap_path=recap_path,
        debug_root=debug_root,
        client=client,
    )
    html = fetched_page.debug_path.read_text(encoding="utf-8")
    try:
        rows = parse_ticker_flow_history(
            html,
            source_date=fetched_page.source_date,
            symbol=fetched_page.symbol,
        )
    except ParserError as exc:
        raise IngestError(str(exc)) from exc

    observation_path = (
        output_root / "ticker_flow" / fetched_page.symbol / f"{source_date.isoformat()}.jsonl"
    )
    observation_path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row.to_dict(), sort_keys=True) + "\n" for row in rows)
    observation_path.write_text(payload, encoding="utf-8")

    logger.bind(
        source_date=source_date.isoformat(),
        symbol=fetched_page.symbol,
        row_count=len(rows),
        observation_path=str(observation_path),
    ).success("Wrote Bulltard ticker-flow observations")
    return TickerIngestResult(
        fetched_page=fetched_page,
        row_count=len(rows),
        observation_path=observation_path,
    )


def ingest_trades_of_interest(
    *,
    source_date: date,
    recap_path: Path,
    output_root: Path = DEFAULT_OBSERVATIONS_ROOT,
) -> TradesOfInterestIngestResult:
    """Parse and write Trades Of Interest observations from one local recap."""

    if not recap_path.is_file():
        raise IngestError(f"Recap path does not exist or is not a file: {recap_path}")
    _warn_if_path_date_differs(source_date=source_date, path=recap_path)

    logger.bind(
        source_date=source_date.isoformat(),
        recap_path=str(recap_path),
    ).info("Parsing Bulltard Trades Of Interest")
    rows = extract_trades_of_interest(
        recap_path.read_text(encoding="utf-8"),
        source_date=source_date,
    )
    if not rows:
        raise IngestError("No Trades Of Interest entries found in recap")

    observation_path = output_root / "trades_of_interest" / f"{source_date.isoformat()}.jsonl"
    observation_path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row.to_dict(), sort_keys=True) + "\n" for row in rows)
    observation_path.write_text(payload, encoding="utf-8")

    symbols = tuple(row.symbol for row in rows)
    logger.bind(
        source_date=source_date.isoformat(),
        row_count=len(rows),
        symbols=symbols,
        observation_path=str(observation_path),
    ).success("Wrote Bulltard Trades Of Interest observations")
    return TradesOfInterestIngestResult(
        source_date=source_date,
        recap_path=recap_path,
        row_count=len(rows),
        observation_path=observation_path,
        symbols=symbols,
    )


def normalize_ticker_symbol(symbol: str) -> str:
    """Normalize and validate a ticker symbol for a Bulltard ticker route."""

    normalized = symbol.strip().upper()
    if not _TICKER_RE.fullmatch(normalized):
        raise IngestError(f"Invalid ticker symbol: {symbol}")
    return normalized


def _parse_fetched_view(fetched_view: FetchedView):
    html = fetched_view.debug_path.read_text(encoding="utf-8")
    try:
        match fetched_view.plan.view:
            case BulltardView.RANKED_OPTION_TRADES:
                return parse_ranked_option_trades(
                    html,
                    source_date=fetched_view.plan.source_date,
                )
    except ParserError as exc:
        raise IngestError(str(exc)) from exc


def _get(client: httpx.Client, url: str, *, purpose: str) -> httpx.Response:
    try:
        return client.get(url)
    except httpx.HTTPError as exc:
        raise IngestError(f"Failed to retrieve Bulltard {purpose}: {exc}") from exc


def _require_app_access(response: httpx.Response) -> None:
    _require_usable_response(response, label="bootstrap")
    parts = urlsplit(str(response.url))
    if parts.scheme != "https" or parts.netloc.lower() != APP_HOST:
        raise IngestError(
            f"Signed URL did not establish Bulltard app access; ended at {response.url}"
        )


def _require_usable_response(response: httpx.Response, *, label: str) -> None:
    if response.status_code >= 400:
        raise IngestError(f"Bulltard {label} request failed with HTTP {response.status_code}")
    if not response.content:
        raise IngestError(f"Bulltard {label} response was empty")


def _warn_if_path_date_differs(*, source_date: date, path: Path) -> None:
    match = _DATE_IN_NAME_RE.search(path.name)
    if not match:
        return
    try:
        path_date = date.fromisoformat(match.group(0))
    except ValueError:
        return
    if path_date != source_date:
        logger.bind(
            source_date=source_date.isoformat(),
            path_date=path_date.isoformat(),
            path=str(path),
        ).warning("Recap filename date differs from --date")
