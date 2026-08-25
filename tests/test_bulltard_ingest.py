import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from marketlab.bulltard.ingest import (
    IngestError,
    build_ingest_plan,
    fetch_ingest_view,
    ingest_planned_view,
)
from marketlab.bulltard.models import BulltardView

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bulltard"


def test_build_ingest_plan_resolves_signed_url_and_observation_path(tmp_path: Path) -> None:
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
    assert plan.observation_path == output_root / "ranked_option_trades" / "2026-08-24.jsonl"


def test_build_ingest_plan_fails_for_missing_recap(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="Recap path does not exist"):
        build_ingest_plan(
            source_date=date(2026, 8, 24),
            view=BulltardView.RANKED_OPTION_TRADES,
            recap_path=tmp_path / "missing.html",
        )


def test_fetch_ingest_view_uses_signed_link_session_and_writes_debug_html(
    tmp_path: Path,
) -> None:
    debug_root = tmp_path / "debug" / "bulltard"
    plan = build_ingest_plan(
        source_date=date(2026, 8, 24),
        view=BulltardView.RANKED_OPTION_TRADES,
        recap_path=FIXTURE_DIR / "recap.html",
    )
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(f"{request.url.host}{request.url.path}")
        if request.url.host == "jamesbulltard.substack.com":
            return httpx.Response(
                302,
                headers={"location": "https://app.jamesbulltard.com/"},
            )
        if request.url.path == "/":
            return httpx.Response(
                200,
                headers={"set-cookie": "bulltard_session=fixture-session; Path=/"},
                content=b"<html>home</html>",
            )
        if request.url.path == "/ranked_option_trades":
            assert request.headers["cookie"] == "bulltard_session=fixture-session"
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"<html>ranked trades</html>",
            )
        return httpx.Response(404)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    result = fetch_ingest_view(plan, debug_root=debug_root, client=client)

    assert requested_paths == [
        "jamesbulltard.substack.com/redirect",
        "app.jamesbulltard.com/",
        "app.jamesbulltard.com/ranked_option_trades",
    ]
    assert result.status_code == 200
    assert result.content_type == "text/html"
    assert result.byte_count == len(b"<html>ranked trades</html>")
    assert result.debug_path == debug_root / "ranked_option_trades" / "2026-08-24.html"
    assert result.debug_path.read_bytes() == b"<html>ranked trades</html>"


def test_fetch_ingest_view_fails_without_app_bootstrap(tmp_path: Path) -> None:
    plan = build_ingest_plan(
        source_date=date(2026, 8, 24),
        view=BulltardView.RANKED_OPTION_TRADES,
        recap_path=FIXTURE_DIR / "recap.html",
    )
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, content=b"<html>substack</html>")
        ),
        follow_redirects=True,
    )

    with pytest.raises(IngestError, match="did not establish Bulltard app access"):
        fetch_ingest_view(plan, debug_root=tmp_path / "debug", client=client)


def test_ingest_planned_view_writes_ranked_trade_observations(tmp_path: Path) -> None:
    output_root = tmp_path / "observations" / "bulltard"
    debug_root = tmp_path / "debug" / "bulltard"
    ranked_html = (FIXTURE_DIR / "ranked_option_trades.html").read_bytes()
    plan = build_ingest_plan(
        source_date=date(2026, 8, 25),
        view=BulltardView.RANKED_OPTION_TRADES,
        recap_path=FIXTURE_DIR / "recap.html",
        output_root=output_root,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "jamesbulltard.substack.com":
            return httpx.Response(302, headers={"location": "https://app.jamesbulltard.com/"})
        if request.url.path == "/":
            return httpx.Response(200, content=b"<html>home</html>")
        if request.url.path == "/ranked_option_trades":
            return httpx.Response(200, headers={"content-type": "text/html"}, content=ranked_html)
        return httpx.Response(404)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    result = ingest_planned_view(plan, debug_root=debug_root, client=client)

    assert result.row_count == 3
    assert result.observation_path == output_root / "ranked_option_trades" / "2026-08-25.jsonl"
    rows = [
        json.loads(line)
        for line in result.observation_path.read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["symbol"] == "INTC"
    assert rows[0]["side"] == "bullish"
    assert rows[0]["premium"] == 74508194.5
    assert rows[2]["symbol"] == "AKAM"
    assert rows[2]["side"] == "bearish"
