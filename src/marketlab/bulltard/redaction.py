"""Helpers for keeping credential-bearing URLs out of ordinary logs and manifests."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "REDACTED"


def redact_url(url: str) -> str:
    """Redact query-string values and fragments while preserving route shape.

    Signed recap links and application scanner links are capability URLs. For routine
    manifests and logs we keep the host, path, and parameter names, but not values.
    """

    parts = urlsplit(url)
    query = urlencode(
        [(key, REDACTED) for key, _value in parse_qsl(parts.query, keep_blank_values=True)],
        doseq=True,
    )
    fragment = REDACTED if parts.fragment else ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, fragment))
