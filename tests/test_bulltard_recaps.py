from datetime import date
from pathlib import Path

import pytest

from marketlab.bulltard.recaps import (
    SignedSourceUrlError,
    extract_signed_source_url,
    extract_trades_of_interest,
    extract_urls,
    looks_like_signed_source_url,
    redact_capability_url,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bulltard"


def test_extract_signed_source_url_from_recap_fixture() -> None:
    recap = (FIXTURE_DIR / "recap.html").read_text(encoding="utf-8")

    signed_url = extract_signed_source_url(recap)

    assert signed_url.startswith("https://jamesbulltard.substack.com/redirect?")
    assert "fixture-secret" in signed_url


def test_extract_urls_deduplicates_text_and_html_urls() -> None:
    text = """
    <a href="https://jamesbulltard.substack.com/redirect?token=abc">link</a>
    https://jamesbulltard.substack.com/redirect?token=abc.
    """

    assert extract_urls(text) == ("https://jamesbulltard.substack.com/redirect?token=abc",)


def test_redact_capability_url_masks_signed_and_nested_tokens() -> None:
    redacted = redact_capability_url(
        "https://jamesbulltard.substack.com/redirect?"
        "url=https%3A%2F%2Fapp.jamesbulltard.com%2Fscanner%2F%3Faccess_token%3Dscanner-secret"
        "&token=fixture-secret&expires=2026-08-24T21%3A00%3A00Z"
    )

    assert redacted == (
        "https://jamesbulltard.substack.com/redirect?"
        "url=https%3A%2F%2Fapp.jamesbulltard.com%2Fscanner%2F%3Faccess_token%3Dredacted"
        "&token=redacted&expires=2026-08-24T21%3A00%3A00Z"
    )
    assert "fixture-secret" not in redacted
    assert "scanner-secret" not in redacted


def test_extract_signed_source_url_unwraps_gmail_tracking_redirect() -> None:
    recap = (FIXTURE_DIR / "gmail_wrapped_database_link.html").read_text(encoding="utf-8")

    signed_url = extract_signed_source_url(recap)

    assert signed_url == (
        "https://substack.com/redirect/00000000-0000-4000-8000-000000000000?j=fixture-jwt"
    )


def test_looks_like_signed_source_url_accepts_signed_redirect_or_encoded_app_target() -> None:
    assert looks_like_signed_source_url(
        "https://substack.com/redirect/00000000-0000-4000-8000-000000000000?j=fixture-jwt"
    )
    assert looks_like_signed_source_url(
        "https://jamesbulltard.substack.com/redirect?"
        "url=https%3A%2F%2Fapp.jamesbulltard.com%2Franked_option_trades&token=abc"
    )
    assert not looks_like_signed_source_url("https://jamesbulltard.substack.com/redirect?token=abc")
    assert not looks_like_signed_source_url("https://jamesbulltard.substack.com/redirect")
    assert not looks_like_signed_source_url(
        "https://app.jamesbulltard.com/scanner/?access_token=abc"
    )


def test_extract_signed_source_url_fails_without_candidate() -> None:
    with pytest.raises(SignedSourceUrlError, match="No signed Bulltard app bootstrap URL found"):
        extract_signed_source_url("no links here")


def test_extract_signed_source_url_ignores_gmail_export_substack_post_links() -> None:
    recap = (FIXTURE_DIR / "gmail_export_without_database_link.html").read_text(encoding="utf-8")

    with pytest.raises(SignedSourceUrlError, match="No signed Bulltard app bootstrap URL found"):
        extract_signed_source_url(recap)


def test_extract_trades_of_interest_reads_ordered_list_items() -> None:
    recap = (FIXTURE_DIR / "trades_of_interest.html").read_text(encoding="utf-8")

    rows = extract_trades_of_interest(recap, source_date=date(2026, 8, 26))

    assert len(rows) == 2
    assert rows[0].to_dict() == {
        "source": "bulltard",
        "source_date": "2026-08-26",
        "view": "trades-of-interest",
        "rank": 1,
        "symbol": "META",
        "note": "$640 calls in October bought 3000x for 10.25. First note.",
    }
    assert rows[1].symbol == "XAR"
    assert rows[1].note.startswith("$240 puts sold")


def test_extract_trades_of_interest_returns_empty_tuple_when_section_is_absent() -> None:
    rows = extract_trades_of_interest("<html></html>", source_date=date(2026, 8, 26))

    assert rows == ()
