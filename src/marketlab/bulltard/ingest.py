"""Prepare targeted Bulltard ingestion runs."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from loguru import logger

from marketlab.bulltard.models import BulltardView, IngestPlan
from marketlab.bulltard.recaps import SignedSourceUrlError, extract_signed_source_url

DEFAULT_OBSERVATIONS_ROOT = Path("data/observations/bulltard")


class IngestError(ValueError):
    """Raised when a Bulltard ingest run cannot be prepared."""


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

    output_path = output_root / view.output_slug / f"{source_date.isoformat()}.jsonl"
    plan = IngestPlan(
        source_date=source_date,
        view=view,
        recap_path=recap_path,
        signed_url=signed_url,
        output_path=output_path,
    )
    logger.bind(
        source_date=source_date.isoformat(),
        view=view.value,
        route_path=view.route_path,
        output_path=str(output_path),
    ).success("Prepared Bulltard ingest plan")
    return plan
