import base64
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from marketlab.gmail import (
    GmailBulltardRecapResult,
    fetch_bulltard_recap_from_gmail,
    gmail_credentials_available,
)


def test_gmail_credentials_available_requires_client_secret_and_token(tmp_path: Path) -> None:
    client_secret_path = tmp_path / "client-secret.json"
    token_path = tmp_path / "token.json"

    assert not gmail_credentials_available(
        client_secret_path=client_secret_path,
        token_path=token_path,
    )

    client_secret_path.write_text("{}", encoding="utf-8")
    token_path.write_text("{}", encoding="utf-8")

    assert gmail_credentials_available(
        client_secret_path=client_secret_path,
        token_path=token_path,
    )


def test_fetch_bulltard_recap_from_gmail_searches_messages_and_caches_html(
    tmp_path: Path,
) -> None:
    client_secret_path = _write_client_secret(tmp_path)
    token_path = _write_token(tmp_path, access_token="access-token")
    output_root = tmp_path / "inbox"
    client = _FakeGmailClient()

    result = fetch_bulltard_recap_from_gmail(
        source_date=date(2026, 9, 1),
        client_secret_path=client_secret_path,
        token_path=token_path,
        output_root=output_root,
        client=client,
    )

    assert isinstance(result, GmailBulltardRecapResult)
    assert result.message_id == "message-1"
    assert result.thread_id == "thread-1"
    assert result.subject == "9/1/26 Recap"
    assert result.sender == "James <james@example.com>"
    assert result.signed_url == (
        "https://substack.com/redirect/00000000-0000-4000-8000-000000000000?j=fixture-jwt"
    )
    assert result.recap_path == output_root / "recap-2026-09-01.html"
    assert "substack.com/redirect" in result.recap_path.read_text(encoding="utf-8")
    assert client.search_queries == ("Bulltard after:2026/09/01 before:2026/09/02",)
    assert client.auth_headers == ("Bearer access-token", "Bearer access-token")


def test_fetch_bulltard_recap_from_gmail_refreshes_expired_token(tmp_path: Path) -> None:
    client_secret_path = _write_client_secret(tmp_path)
    token_path = _write_token(tmp_path, access_token="expired-token", expires_at_epoch=1)
    client = _FakeGmailClient(refreshed_access_token="fresh-token")

    fetch_bulltard_recap_from_gmail(
        source_date=date(2026, 9, 1),
        client_secret_path=client_secret_path,
        token_path=token_path,
        output_root=tmp_path / "inbox",
        client=client,
    )

    stored_token = json.loads(token_path.read_text(encoding="utf-8"))
    assert stored_token["access_token"] == "fresh-token"
    assert stored_token["refresh_token"] == "refresh-token"
    assert client.token_refresh_count == 1
    assert client.auth_headers == ("Bearer fresh-token", "Bearer fresh-token")


def _write_client_secret(tmp_path: Path) -> Path:
    path = tmp_path / "client-secret.json"
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "fixture-client-id",
                    "client_secret": "fixture-client-secret",
                    "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_token(
    tmp_path: Path,
    *,
    access_token: str,
    expires_at_epoch: int | None = None,
) -> Path:
    path = tmp_path / "token.json"
    path.write_text(
        json.dumps(
            {
                "access_token": access_token,
                "refresh_token": "refresh-token",
                "scope": "https://www.googleapis.com/auth/gmail.readonly",
                "token_type": "Bearer",
                "expires_at_epoch": expires_at_epoch or int(time.time()) + 3600,
            }
        ),
        encoding="utf-8",
    )
    return path


def _gmail_body_payload(html: str) -> dict[str, Any]:
    encoded = base64.urlsafe_b64encode(html.encode("utf-8")).decode("ascii").rstrip("=")
    return {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {
                    "data": base64.urlsafe_b64encode(b"plain fallback").decode("ascii").rstrip("="),
                },
            },
            {
                "mimeType": "text/html",
                "body": {"data": encoded},
            },
        ],
    }


class _FakeGmailClient:
    def __init__(self, *, refreshed_access_token: str | None = None) -> None:
        self.refreshed_access_token = refreshed_access_token
        self.search_queries: tuple[str, ...] = ()
        self.auth_headers: tuple[str, ...] = ()
        self.token_refresh_count = 0

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, object],
    ) -> httpx.Response:
        self.auth_headers = (*self.auth_headers, headers["Authorization"])
        if url.endswith("/users/me/messages"):
            self.search_queries = (*self.search_queries, str(params["q"]))
            return httpx.Response(200, json={"messages": [{"id": "message-1"}]})
        if url.endswith("/users/me/messages/message-1"):
            return httpx.Response(
                200,
                json={
                    "id": "message-1",
                    "threadId": "thread-1",
                    "internalDate": "1788302400000",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "9/1/26 Recap"},
                            {"name": "From", "value": "James <james@example.com>"},
                        ],
                        **_gmail_body_payload(
                            '<a href="https://substack.com/redirect/'
                            '00000000-0000-4000-8000-000000000000?j=fixture-jwt">'
                            "Database link</a>"
                        ),
                    },
                },
            )
        raise AssertionError(f"Unexpected GET URL: {url}")

    def post(self, url: str, *, data: dict[str, str]) -> httpx.Response:
        assert url == "https://oauth2.googleapis.com/token"
        assert data["refresh_token"] == "refresh-token"
        self.token_refresh_count += 1
        return httpx.Response(
            200,
            json={
                "access_token": self.refreshed_access_token or "access-token",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/gmail.readonly",
                "token_type": "Bearer",
            },
        )

    def close(self) -> None:
        return
