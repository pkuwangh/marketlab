import hashlib
from datetime import UTC, date, datetime

from marketlab.bulltard.models import CaptureManifest, RawArtifact
from marketlab.bulltard.redaction import REDACTED


def test_raw_artifact_hashes_payload_bytes() -> None:
    payload = b"<html><body>MU</body></html>"
    artifact = RawArtifact.from_bytes(
        route_name="scanner",
        path="data/raw/bulltard/2026-08-24/scanner.html",
        source_url="https://app.jamesbulltard.com/scanner/?access_token=secret",
        final_url="https://app.jamesbulltard.com/scanner/?access_token=secret",
        payload=payload,
        status_code=200,
        content_type="text/html",
        captured_at=datetime(2026, 8, 24, 21, 0, tzinfo=UTC),
    )

    assert artifact.sha256 == hashlib.sha256(payload).hexdigest()
    assert artifact.byte_count == len(payload)


def test_manifest_json_redacts_urls_by_default() -> None:
    artifact = RawArtifact.from_bytes(
        route_name="scanner",
        path="data/raw/bulltard/2026-08-24/scanner.html",
        source_url="https://app.jamesbulltard.com/scanner/?access_token=super-secret",
        final_url="https://app.jamesbulltard.com/scanner/?access_token=super-secret",
        payload=b"<html></html>",
        status_code=200,
        content_type="text/html",
        captured_at=datetime(2026, 8, 24, 21, 0, tzinfo=UTC),
    )
    manifest = CaptureManifest(
        source_date=date(2026, 8, 24),
        capture_version="bulltard_capture_v0",
        created_at=datetime(2026, 8, 24, 21, 1, tzinfo=UTC),
        artifacts=(artifact,),
    )

    text = manifest.to_json()

    assert "super-secret" not in text
    assert f"access_token={REDACTED}" in text
    assert artifact.sha256 in text


def test_manifest_round_trips_redacted_storage_json() -> None:
    artifact = RawArtifact.from_bytes(
        route_name="rankings",
        path="data/raw/bulltard/2026-08-24/ranked_option_trades.html",
        source_url="https://app.jamesbulltard.com/ranked_option_trades",
        final_url="https://app.jamesbulltard.com/ranked_option_trades",
        payload=b"rankings",
        status_code=200,
        content_type="text/html",
        captured_at=datetime(2026, 8, 24, 21, 0, tzinfo=UTC),
    )
    manifest = CaptureManifest(
        source_date=date(2026, 8, 24),
        capture_version="bulltard_capture_v0",
        created_at=datetime(2026, 8, 24, 21, 1, tzinfo=UTC),
        artifacts=(artifact,),
        errors=("daily_option_trades failed: 403",),
    )

    restored = CaptureManifest.from_json(manifest.to_json())

    assert restored.source_date == manifest.source_date
    assert restored.capture_version == manifest.capture_version
    assert restored.is_partial
    assert restored.artifacts[0].sha256 == artifact.sha256
