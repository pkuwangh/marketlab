"""Discover and classify authorized Bulltard application links."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from loguru import logger

AUTHORIZED_HOST = "app.jamesbulltard.com"


@dataclass(frozen=True, slots=True)
class DiscoveredLink:
    """A same-origin Bulltard research route discovered from archived HTML."""

    url: str
    route_name: str
    path: str


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def extract_hrefs(html: str) -> list[str]:
    """Return href attributes from an HTML document."""

    parser = _HrefParser()
    parser.feed(html)
    return parser.hrefs


def classify_research_url(url: str) -> DiscoveredLink | None:
    """Classify a canonical Bulltard application URL if it is in the v0 crawl boundary."""

    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc.lower() != AUTHORIZED_HOST:
        return None

    path = parts.path or "/"
    route_name = _route_name_for_path(path)
    if route_name is None:
        return None

    return DiscoveredLink(url=url, route_name=route_name, path=path)


def discover_research_links(html: str, *, base_url: str) -> tuple[DiscoveredLink, ...]:
    """Discover unique authorized research links from one archived Bulltard page."""

    hrefs = extract_hrefs(html)
    accepted: dict[str, DiscoveredLink] = {}
    rejected_count = 0

    for href in hrefs:
        canonical_url = canonicalize_url(urljoin(base_url, href))
        link = classify_research_url(canonical_url)
        if link is None:
            rejected_count += 1
            logger.bind(url=canonical_url).debug("Rejected Bulltard link outside v0 boundary")
            continue
        accepted[link.url] = link

    logger.bind(
        base_url=base_url,
        href_count=len(hrefs),
        accepted_count=len(accepted),
        rejected_count=rejected_count,
    ).info("Discovered Bulltard research links")
    return tuple(accepted.values())


def canonicalize_url(url: str) -> str:
    """Normalize scheme and host while preserving path and query parameters exactly."""

    parts = urlsplit(url)
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            parts.query,
            "",
        )
    )


def _route_name_for_path(path: str) -> str | None:
    normalized = path.rstrip("/") or "/"
    if normalized == "/":
        return "home"
    if normalized in {
        "/ranked_option_trades",
        "/daily_option_trades",
        "/bullish_gainers",
        "/sector_rankings",
    }:
        return normalized.removeprefix("/")
    if normalized == "/scanner":
        return "scanner"
    if _is_ticker_path(normalized):
        return "ticker"
    return None


def _is_ticker_path(path: str) -> bool:
    prefix = "/tickers/"
    if not path.startswith(prefix):
        return False
    ticker = path.removeprefix(prefix)
    return bool(ticker) and "/" not in ticker
