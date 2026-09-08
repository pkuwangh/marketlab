"""Extract Bulltard source links from local recap artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from loguru import logger

from marketlab.bulltard.models import TradeOfInterestObservation

_RAW_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_TRADE_OF_INTEREST_ITEM_RE = re.compile(
    "^\\s*([A-Z][A-Z0-9.-]{0,15})\\s*(?:-|:|\\u2013|\\u2014)\\s*(.+)$"
)
_TRAILING_PUNCTUATION = ".,);]"
_BULLTARD_APP_HOST = "app.jamesbulltard.com"
_CONTEXT_CHARS = 500
_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "auth_token",
    "j",
    "jwt",
    "sig",
    "signature",
    "token",
}
_REDACTED_VALUE = "redacted"


@dataclass(frozen=True, slots=True)
class _UrlCandidate:
    url: str
    label: str = ""
    context_before: str = ""


class SignedSourceUrlError(ValueError):
    """Raised when a recap does not contain exactly one signed source URL."""


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[_UrlCandidate] = []
        self._active_href: str | None = None
        self._active_label_parts: list[str] = []
        self._active_context_before = ""
        self._text_tail = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_by_key = {key.lower(): value for key, value in attrs if value}
        if tag.lower() == "a" and attrs_by_key.get("href"):
            self._active_href = attrs_by_key["href"]
            self._active_label_parts = []
            self._active_context_before = self._text_tail
            return

        src = attrs_by_key.get("src")
        if src:
            self.links.append(_UrlCandidate(url=src, context_before=self._text_tail))

    def handle_data(self, data: str) -> None:
        if self._active_href is not None:
            self._active_label_parts.append(data)
            return
        self._append_visible_text(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._active_href is None:
            return

        label = _normalize_text(" ".join(self._active_label_parts))
        self.links.append(
            _UrlCandidate(
                url=self._active_href,
                label=label,
                context_before=self._active_context_before,
            )
        )
        self._append_visible_text(label)
        self._active_href = None
        self._active_label_parts = []
        self._active_context_before = ""

    def _append_visible_text(self, text: str) -> None:
        normalized = _normalize_text(text)
        if not normalized:
            return
        self._text_tail = f"{self._text_tail} {normalized}"[-_CONTEXT_CHARS:]


class _TradesOfInterestParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[str] = []
        self._strong_depth = 0
        self._strong_parts: list[str] = []
        self._awaiting_list = False
        self._list_depth = 0
        self._in_item = False
        self._seen_item_paragraph = False
        self._paragraph_depth = 0
        self._item_parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()

        if self._strong_depth:
            self._strong_depth += 1
        elif tag == "strong":
            self._strong_depth = 1
            self._strong_parts = []

        if self._awaiting_list and tag == "ol":
            self._awaiting_list = False
            self._list_depth = 1
            return

        if not self._list_depth:
            return

        if tag == "ol":
            self._list_depth += 1
            return

        if tag == "li" and not self._in_item:
            self._in_item = True
            self._seen_item_paragraph = False
            self._item_parts = []
            return

        if self._paragraph_depth:
            self._paragraph_depth += 1

        if tag == "p" and self._in_item and not self._seen_item_paragraph:
            self._paragraph_depth = 1
            self._seen_item_paragraph = True
            self._item_parts = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._strong_depth:
            self._strong_parts.append(data)
        if self._paragraph_depth:
            self._item_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if self._strong_depth:
            self._strong_depth -= 1
            if not self._strong_depth and _normalize_text("".join(self._strong_parts)).lower() == (
                "trades of interest"
            ):
                self._awaiting_list = True

        if self._paragraph_depth:
            self._paragraph_depth -= 1
            if not self._paragraph_depth:
                item = _normalize_text("".join(self._item_parts))
                if item:
                    self.items.append(item)

        if tag == "li" and self._in_item:
            self._in_item = False

        if self._list_depth and tag == "ol":
            self._list_depth -= 1


def extract_urls(text_or_html: str) -> tuple[str, ...]:
    """Extract HTTP URLs from plain text and simple HTML attributes."""

    urls = [candidate.url for candidate in _extract_url_candidates(text_or_html)]

    logger.bind(url_count=len(urls)).info("Extracted URLs from recap")
    return tuple(urls)


def extract_trades_of_interest(
    text_or_html: str,
    *,
    source_date: date,
) -> tuple[TradeOfInterestObservation, ...]:
    """Extract ticker notes from a recap's Trades Of Interest section."""

    parser = _TradesOfInterestParser()
    parser.feed(text_or_html)

    observations: list[TradeOfInterestObservation] = []
    for rank, item in enumerate(parser.items, start=1):
        match = _TRADE_OF_INTEREST_ITEM_RE.match(item)
        if not match:
            logger.bind(rank=rank, text=item[:120]).warning(
                "Skipped Trades Of Interest item without a leading ticker"
            )
            continue
        observations.append(
            TradeOfInterestObservation(
                source_date=source_date,
                rank=rank,
                symbol=match.group(1).upper(),
                note=match.group(2),
            )
        )

    logger.bind(
        source_date=source_date.isoformat(),
        item_count=len(parser.items),
        observation_count=len(observations),
    ).info("Extracted Trades Of Interest from recap")
    return tuple(observations)


def extract_signed_source_url(text_or_html: str) -> str:
    """Find the single signed recap URL that bootstraps Bulltard application access."""

    candidates = [
        candidate
        for candidate in _extract_url_candidates(text_or_html)
        if looks_like_signed_source_url(candidate.url)
    ]
    logger.bind(candidate_count=len(candidates)).info("Identified signed source URL candidates")

    if not candidates:
        raise SignedSourceUrlError(
            "No signed Bulltard app bootstrap URL found. Save the recap artifact that contains "
            "the original database/app link, or copy that link into a local text file."
        )
    if len(candidates) > 1:
        selected = _select_database_candidate(candidates)
        if selected is not None:
            logger.bind(
                url=redact_capability_url(selected.url),
                label=selected.label,
            ).info("Selected signed Bulltard source URL from database-link context")
            return selected.url

        raise SignedSourceUrlError(
            "Expected one signed source URL, found "
            f"{len(candidates)}: "
            f"{', '.join(redact_capability_url(candidate.url) or '' for candidate in candidates)}"
        )

    signed_url = candidates[0].url
    logger.bind(url=redact_capability_url(signed_url)).info("Selected signed Bulltard source URL")
    return signed_url


def redact_capability_url(url: str | None) -> str | None:
    """Redact temporary URL capability tokens while keeping debugging context."""

    if url is None:
        return None
    parts = urlsplit(url)
    if not parts.query:
        return url

    redacted_pairs: list[tuple[str, str]] = []
    changed = False
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in _SENSITIVE_QUERY_KEYS:
            redacted_pairs.append((key, _REDACTED_VALUE))
            changed = True
            continue
        nested = redact_capability_url(value) if _looks_like_url(value) else value
        if nested != value:
            changed = True
        redacted_pairs.append((key, nested or ""))

    if not changed:
        return url
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(redacted_pairs, doseq=True),
            parts.fragment,
        )
    )


def looks_like_signed_source_url(url: str) -> bool:
    """Return whether a URL appears to be the signed Substack bootstrap URL.

    Gmail exports include several ordinary Substack post/action links with tokens.
    Those are not useful for database access. Valid source links are either
    Substack redirect capability URLs or links that encode the Bulltard app host.
    """

    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc or not parts.query:
        return False

    host = parts.netloc.lower()
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    query_keys = {key.lower() for key, _value in query_pairs}
    query_values = [value for _key, value in query_pairs]

    if not (host == "substack.com" or host.endswith(".substack.com")):
        return False

    if host == "substack.com" and parts.path.startswith("/redirect/") and "j" in query_keys:
        return True

    targets_bulltard_app = any(_targets_bulltard_app(value) for value in query_values)

    return targets_bulltard_app


def _extract_url_candidates(text_or_html: str) -> tuple[_UrlCandidate, ...]:
    parser = _LinkParser()
    parser.feed(text_or_html)

    raw_candidates = [_UrlCandidate(url=url) for url in _RAW_URL_RE.findall(text_or_html)]
    candidates = [*parser.links, *raw_candidates]

    urls: list[_UrlCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        for expanded in _candidate_urls(candidate):
            if expanded.url in seen:
                continue
            seen.add(expanded.url)
            urls.append(expanded)

    return tuple(urls)


def _candidate_urls(candidate: _UrlCandidate) -> tuple[_UrlCandidate, ...]:
    cleaned = _clean_url(candidate.url)
    if cleaned is None:
        return ()

    unwrapped = _unwrap_google_redirect_url(cleaned)
    if unwrapped is not None:
        return (
            _UrlCandidate(
                url=unwrapped,
                label=candidate.label,
                context_before=candidate.context_before,
            ),
        )

    return (
        _UrlCandidate(
            url=cleaned,
            label=candidate.label,
            context_before=candidate.context_before,
        ),
    )


def _unwrap_google_redirect_url(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.netloc.lower() not in {"google.com", "www.google.com"} or parts.path != "/url":
        return None

    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "q":
            return _clean_url(value)

    return None


def _clean_url(url: str) -> str | None:
    cleaned = unescape(url).strip().rstrip(_TRAILING_PUNCTUATION)
    parts = urlsplit(cleaned)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return cleaned


def _looks_like_url(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def _select_database_candidate(candidates: list[_UrlCandidate]) -> _UrlCandidate | None:
    scored = [(candidate, _database_link_score(candidate)) for candidate in candidates]
    best_score = max(score for _candidate, score in scored)
    if best_score <= 0:
        return None

    best_candidates = [candidate for candidate, score in scored if score == best_score]
    if len(best_candidates) != 1:
        return None
    return best_candidates[0]


def _database_link_score(candidate: _UrlCandidate) -> int:
    label = candidate.label.lower()
    context = candidate.context_before.lower()
    combined = f"{context} {label}"

    score = 0
    if "database link" in context:
        score += 5
    if "today" in context and "database" in context:
        score += 3
    if label in {"link", "database", "database link", "open database"}:
        score += 2
    if any(ignored in combined for ignored in ("view in browser", "unsubscribe", "invite friends")):
        score -= 5
    return score


def _normalize_text(text: str) -> str:
    return " ".join(unescape(text).split())


def _targets_bulltard_app(value: str) -> bool:
    decoded = value
    for _ in range(3):
        if _BULLTARD_APP_HOST in decoded:
            return True
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            return False
        decoded = next_decoded
    return _BULLTARD_APP_HOST in decoded
