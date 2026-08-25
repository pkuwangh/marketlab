from marketlab.bulltard.redaction import REDACTED, redact_url


def test_redact_url_preserves_route_and_query_keys_without_values() -> None:
    url = "https://app.jamesbulltard.com/scanner/?access_token=secret123&symbol=MU#fragsecret"

    redacted = redact_url(url)

    assert redacted.startswith("https://app.jamesbulltard.com/scanner/")
    assert f"access_token={REDACTED}" in redacted
    assert f"symbol={REDACTED}" in redacted
    assert redacted.endswith(f"#{REDACTED}")
    assert "secret123" not in redacted
    assert "fragsecret" not in redacted
    assert "MU" not in redacted


def test_redact_url_leaves_plain_route_unchanged() -> None:
    url = "https://app.jamesbulltard.com/ranked_option_trades"

    assert redact_url(url) == url


def test_redact_url_supports_relative_urls() -> None:
    redacted = redact_url("/scanner/?access_token=abc123")

    assert redacted == f"/scanner/?access_token={REDACTED}"
    assert "abc123" not in redacted
