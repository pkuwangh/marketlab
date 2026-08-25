from datetime import date
from pathlib import Path

import pytest

from marketlab.bulltard.ingest import IngestError, build_ingest_plan
from marketlab.bulltard.models import BulltardView

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bulltard"


def test_build_ingest_plan_resolves_signed_url_and_output_path(tmp_path: Path) -> None:
    output_root = tmp_path / "observations" / "bulltard"

    plan = build_ingest_plan(
        source_date=date(2026, 8, 24),
        view=BulltardView.RANKED_OPTION_TRADES,
        recap_path=FIXTURE_DIR / "recap.html",
        output_root=output_root,
    )

    assert plan.view == BulltardView.RANKED_OPTION_TRADES
    assert plan.view.route_path == "/ranked_option_trades"
    assert plan.signed_url.startswith("https://jamesbulltard.substack.com/redirect?")
    assert "fixture-secret" in plan.signed_url
    assert plan.output_path == output_root / "ranked_option_trades" / "2026-08-24.jsonl"


def test_build_ingest_plan_fails_for_missing_recap(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="Recap path does not exist"):
        build_ingest_plan(
            source_date=date(2026, 8, 24),
            view=BulltardView.RANKED_OPTION_TRADES,
            recap_path=tmp_path / "missing.html",
        )
