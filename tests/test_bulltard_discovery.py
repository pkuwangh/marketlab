from pathlib import Path

from marketlab.bulltard.discovery import classify_research_url, discover_research_links

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bulltard"


def test_discover_research_links_accepts_only_v0_research_routes() -> None:
    html = (FIXTURE_DIR / "app_home.html").read_text(encoding="utf-8")

    links = discover_research_links(html, base_url="https://app.jamesbulltard.com/")

    assert [link.route_name for link in links] == [
        "ranked_option_trades",
        "daily_option_trades",
        "bullish_gainers",
        "sector_rankings",
        "scanner",
        "ticker",
    ]
    assert links[4].url == "https://app.jamesbulltard.com/scanner/?access_token=scanner-secret"


def test_classify_research_url_rejects_off_origin_and_unknown_routes() -> None:
    assert classify_research_url("https://example.com/ranked_option_trades") is None
    assert classify_research_url("https://app.jamesbulltard.com/admin") is None
    assert classify_research_url("http://app.jamesbulltard.com/ranked_option_trades") is None


def test_classify_research_url_accepts_ticker_routes() -> None:
    link = classify_research_url("https://app.jamesbulltard.com/tickers/MU")

    assert link is not None
    assert link.route_name == "ticker"
    assert link.path == "/tickers/MU"
