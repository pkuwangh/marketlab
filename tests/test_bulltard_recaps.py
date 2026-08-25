from pathlib import Path

import pytest

from marketlab.bulltard.recaps import (
    SignedSourceUrlError,
    extract_signed_source_url,
    extract_urls,
    looks_like_signed_source_url,
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
