"""Daily Bulltard research workflow orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from marketlab.bulltard.candidates import (
    CandidateReviewError,
    format_candidate_reviews,
    load_candidate_reviews,
)
from marketlab.bulltard.ingest import (
    DEFAULT_DEBUG_ROOT,
    DEFAULT_OBSERVATIONS_ROOT,
    HTTP_TIMEOUT_SECONDS,
    IngestError,
    IngestResult,
    TickerIngestResult,
    TradesOfInterestIngestResult,
    build_ingest_plan,
    ingest_planned_view,
    ingest_ticker_page,
    ingest_trades_of_interest,
    normalize_ticker_symbol,
)
from marketlab.bulltard.models import BulltardView
from marketlab.bulltard.validation import BENCHMARK_SYMBOLS
from marketlab.prices import (
    DEFAULT_PRICE_OBSERVATIONS_ROOT,
    PriceDataError,
    PriceFetchResult,
    dedupe_symbols,
    fetch_and_write_yahoo_daily_prices,
)


class DailyWorkflowError(ValueError):
    """Raised when a daily Bulltard workflow cannot run."""


@dataclass(frozen=True, slots=True)
class TickerIngestFailure:
    """One failed ticker detail fetch from a daily workflow."""

    symbol: str
    error: str


@dataclass(frozen=True, slots=True)
class PriceRefreshFailure:
    """One failed candidate price refresh."""

    symbol: str
    error: str


@dataclass(frozen=True, slots=True)
class CandidatePriceRefreshResult:
    """Result of refreshing prices for one Bulltard candidate set."""

    source_date: date
    start_date: date
    end_date: date
    requested_symbols: tuple[str, ...]
    price_results: tuple[PriceFetchResult, ...]
    price_failures: tuple[PriceRefreshFailure, ...]


@dataclass(frozen=True, slots=True)
class DailyWorkflowResult:
    """Result of one Bulltard daily workflow run."""

    source_date: date
    ranked_result: IngestResult
    trades_of_interest_result: TradesOfInterestIngestResult | None
    ticker_results: tuple[TickerIngestResult, ...]
    ticker_failures: tuple[TickerIngestFailure, ...]
    candidate_table: str


def run_daily_workflow(
    *,
    source_date: date,
    recap_path: Path,
    output_root: Path = DEFAULT_OBSERVATIONS_ROOT,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
    fetch_ticker_details: bool = True,
    top_ranked: int = 0,
    extra_tickers: tuple[str, ...] = (),
    limit: int = 12,
    client: httpx.Client | None = None,
) -> DailyWorkflowResult:
    """Run the daily Bulltard candidate loop."""

    logger.bind(
        source_date=source_date.isoformat(),
        recap_path=str(recap_path),
        top_ranked=top_ranked,
        extra_tickers=extra_tickers,
        fetch_ticker_details=fetch_ticker_details,
    ).info("Starting Bulltard daily workflow")

    owns_client = client is None
    active_client = client or httpx.Client(
        follow_redirects=True,
        timeout=HTTP_TIMEOUT_SECONDS,
    )

    try:
        trades_result = _try_ingest_trades_of_interest(
            source_date=source_date,
            recap_path=recap_path,
            output_root=output_root,
        )
        ranked_result = _ingest_ranked_view(
            source_date=source_date,
            recap_path=recap_path,
            output_root=output_root,
            debug_root=debug_root,
            client=active_client,
        )

        ticker_results: list[TickerIngestResult] = []
        ticker_failures: list[TickerIngestFailure] = []
        if fetch_ticker_details:
            for symbol in _detail_symbols(
                trades_result=trades_result,
                ranked_observation_path=ranked_result.observation_path,
                top_ranked=top_ranked,
                extra_tickers=extra_tickers,
            ):
                try:
                    ticker_results.append(
                        ingest_ticker_page(
                            source_date=source_date,
                            symbol=symbol,
                            recap_path=recap_path,
                            output_root=output_root,
                            debug_root=debug_root,
                            client=active_client,
                        )
                    )
                except IngestError as exc:
                    failure = TickerIngestFailure(symbol=symbol, error=str(exc))
                    ticker_failures.append(failure)
                    logger.bind(
                        source_date=source_date.isoformat(),
                        symbol=symbol,
                        error=str(exc),
                    ).error("Failed Bulltard ticker detail ingest")

        try:
            reviews = load_candidate_reviews(
                source_date=source_date,
                observations_root=output_root,
                limit=limit,
            )
        except CandidateReviewError as exc:
            raise DailyWorkflowError(str(exc)) from exc

        result = DailyWorkflowResult(
            source_date=source_date,
            ranked_result=ranked_result,
            trades_of_interest_result=trades_result,
            ticker_results=tuple(ticker_results),
            ticker_failures=tuple(ticker_failures),
            candidate_table=format_candidate_reviews(reviews),
        )
        logger.bind(
            source_date=source_date.isoformat(),
            ranked_rows=ranked_result.row_count,
            trades_of_interest_rows=trades_result.row_count if trades_result else 0,
            ticker_successes=len(ticker_results),
            ticker_failures=len(ticker_failures),
        ).success("Completed Bulltard daily workflow")
        return result
    finally:
        if owns_client:
            active_client.close()


def refresh_candidate_prices(
    *,
    source_date: date,
    start_date: date,
    end_date: date,
    observations_root: Path = DEFAULT_OBSERVATIONS_ROOT,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    limit: int = 12,
    extra_symbols: tuple[str, ...] = BENCHMARK_SYMBOLS,
    downloader=None,
) -> CandidatePriceRefreshResult:
    """Refresh Yahoo price observations for Bulltard candidates and benchmarks."""

    if end_date < start_date:
        raise DailyWorkflowError("Price refresh end date must be on or after start date")

    try:
        reviews = load_candidate_reviews(
            source_date=source_date,
            observations_root=observations_root,
            limit=limit,
        )
    except CandidateReviewError as exc:
        raise DailyWorkflowError(str(exc)) from exc

    requested_symbols = dedupe_symbols(
        tuple(review.symbol for review in reviews) + tuple(extra_symbols)
    )
    price_results: list[PriceFetchResult] = []
    price_failures: list[PriceRefreshFailure] = []
    for symbol in requested_symbols:
        try:
            price_results.extend(
                fetch_and_write_yahoo_daily_prices(
                    symbols=(symbol,),
                    start_date=start_date,
                    end_date=end_date,
                    output_root=price_root,
                    downloader=downloader,
                )
            )
        except PriceDataError as exc:
            price_failures.append(PriceRefreshFailure(symbol=symbol, error=str(exc)))
            logger.bind(
                source_date=source_date.isoformat(),
                symbol=symbol,
                error=str(exc),
            ).error("Failed candidate price refresh")

    result = CandidatePriceRefreshResult(
        source_date=source_date,
        start_date=start_date,
        end_date=end_date,
        requested_symbols=requested_symbols,
        price_results=tuple(price_results),
        price_failures=tuple(price_failures),
    )
    logger.bind(
        source_date=source_date.isoformat(),
        requested_symbols=len(requested_symbols),
        price_successes=len(price_results),
        price_failures=len(price_failures),
        price_root=str(price_root),
    ).success("Refreshed Bulltard candidate prices")
    return result


def _try_ingest_trades_of_interest(
    *,
    source_date: date,
    recap_path: Path,
    output_root: Path,
) -> TradesOfInterestIngestResult | None:
    try:
        return ingest_trades_of_interest(
            source_date=source_date,
            recap_path=recap_path,
            output_root=output_root,
        )
    except IngestError as exc:
        if "No Trades Of Interest entries found" not in str(exc):
            raise DailyWorkflowError(str(exc)) from exc
        logger.bind(
            source_date=source_date.isoformat(),
            recap_path=str(recap_path),
        ).warning("No Bulltard Trades Of Interest section found")
        return None


def _ingest_ranked_view(
    *,
    source_date: date,
    recap_path: Path,
    output_root: Path,
    debug_root: Path,
    client: httpx.Client,
) -> IngestResult:
    try:
        plan = build_ingest_plan(
            source_date=source_date,
            view=BulltardView.RANKED_OPTION_TRADES,
            recap_path=recap_path,
            output_root=output_root,
        )
        return ingest_planned_view(plan, debug_root=debug_root, client=client)
    except IngestError as exc:
        raise DailyWorkflowError(str(exc)) from exc


def _detail_symbols(
    *,
    trades_result: TradesOfInterestIngestResult | None,
    ranked_observation_path: Path,
    top_ranked: int,
    extra_tickers: tuple[str, ...],
) -> tuple[str, ...]:
    symbols: list[str] = []

    if trades_result is not None:
        symbols.extend(trades_result.symbols)
    if top_ranked:
        symbols.extend(_top_ranked_symbols(ranked_observation_path, limit=top_ranked))
    symbols.extend(extra_tickers)

    normalized_symbols = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized = normalize_ticker_symbol(symbol)
        if normalized in seen:
            continue
        seen.add(normalized)
        normalized_symbols.append(normalized)
    return tuple(normalized_symbols)


def _top_ranked_symbols(path: Path, *, limit: int) -> tuple[str, ...]:
    rows = _read_jsonl(path)
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            abs(float(row["score"])),
            float(row["premium"]),
            int(row["trade_count"]),
            str(row["symbol"]),
        ),
        reverse=True,
    )
    return tuple(str(row["symbol"]).upper() for row in sorted_rows[:limit])


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    try:
        return tuple(
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError as exc:
        raise DailyWorkflowError(f"Failed to read observations file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DailyWorkflowError(f"Invalid JSONL observations file: {path}") from exc
