"""Prepare targeted Bulltard ingestion runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from loguru import logger

from marketlab.bulltard.models import BulltardView, IngestPlan
from marketlab.bulltard.recaps import SignedSourceUrlError, extract_signed_source_url

DEFAULT_OBSERVATIONS_ROOT = Path("data/observations/bulltard")
DEFAULT_DEBUG_ROOT = Path("data/debug/bulltard")
APP_HOST = "app.jamesbulltard.com"
APP_ORIGIN = f"https://{APP_HOST}"
HTTP_TIMEOUT_SECONDS = 30.0


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
        _require_usable_response(response, view=plan.view)

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


def _get(client: httpx.Client, url: str, *, purpose: str) -> httpx.Response:
    try:
        return client.get(url)
    except httpx.HTTPError as exc:
        raise IngestError(f"Failed to retrieve Bulltard {purpose}: {exc}") from exc


def _require_app_access(response: httpx.Response) -> None:
    _require_usable_response(response, view=None)
    parts = urlsplit(str(response.url))
    if parts.scheme != "https" or parts.netloc.lower() != APP_HOST:
        raise IngestError(
            f"Signed URL did not establish Bulltard app access; ended at {response.url}"
        )


def _require_usable_response(response: httpx.Response, *, view: BulltardView | None) -> None:
    if response.status_code >= 400:
        label = view.value if view is not None else "bootstrap"
        raise IngestError(f"Bulltard {label} request failed with HTTP {response.status_code}")
    if not response.content:
        label = view.value if view is not None else "bootstrap"
        raise IngestError(f"Bulltard {label} response was empty")
