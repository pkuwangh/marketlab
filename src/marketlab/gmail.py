"""Read Bulltard recap emails from Gmail with read-only OAuth."""

from __future__ import annotations

import base64
import json
import secrets
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from loguru import logger

from marketlab.bulltard.recaps import SignedSourceUrlError, extract_signed_source_url

DEFAULT_GMAIL_CLIENT_SECRET_PATH = Path("secrets/google-oauth-client.json")
DEFAULT_GMAIL_TOKEN_PATH = Path("secrets/gmail-token.json")
DEFAULT_GMAIL_RECAP_CACHE_ROOT = Path("data/inbox/bulltard")
GMAIL_API_ROOT = "https://gmail.googleapis.com/gmail/v1"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
HTTP_TIMEOUT_SECONDS = 30.0
TOKEN_EXPIRY_SKEW_SECONDS = 60


class GmailError(ValueError):
    """Raised when Gmail authorization or recap retrieval fails."""


@dataclass(frozen=True, slots=True)
class GmailAuthResult:
    """Result of a one-time Gmail OAuth authorization."""

    token_path: Path
    scope: str
    expires_at: str | None


@dataclass(frozen=True, slots=True)
class GmailBulltardRecapResult:
    """Result of fetching one Bulltard recap from Gmail."""

    source_date: date
    message_id: str
    thread_id: str | None
    subject: str | None
    sender: str | None
    received_at: str | None
    recap_path: Path
    signed_url: str
    query: str


@dataclass(frozen=True, slots=True)
class _OAuthClientConfig:
    client_id: str
    client_secret: str | None
    auth_uri: str
    token_uri: str


@dataclass(frozen=True, slots=True)
class _OAuthToken:
    access_token: str
    refresh_token: str | None
    scope: str | None
    token_type: str | None
    expires_at_epoch: int | None


def gmail_credentials_available(
    *,
    client_secret_path: Path = DEFAULT_GMAIL_CLIENT_SECRET_PATH,
    token_path: Path = DEFAULT_GMAIL_TOKEN_PATH,
) -> bool:
    """Return whether Gmail has enough local credentials to try API access."""

    return client_secret_path.is_file() and token_path.is_file()


def run_gmail_oauth_flow(
    *,
    client_secret_path: Path = DEFAULT_GMAIL_CLIENT_SECRET_PATH,
    token_path: Path = DEFAULT_GMAIL_TOKEN_PATH,
    port: int = 0,
    open_browser: bool = True,
    timeout_seconds: int = 300,
    auth_url_callback: Callable[[str], None] | None = None,
    client: httpx.Client | None = None,
) -> GmailAuthResult:
    """Run a local loopback OAuth flow and store a Gmail read-only token."""

    if timeout_seconds <= 0:
        raise GmailError("OAuth timeout must be positive")

    config = _load_oauth_client_config(client_secret_path)
    state = secrets.token_urlsafe(18)

    server = _OAuthCallbackServer(("127.0.0.1", port), _OAuthCallbackHandler)
    server.timeout = timeout_seconds
    actual_port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{actual_port}/"
    auth_url = _build_authorization_url(
        config=config,
        redirect_uri=redirect_uri,
        state=state,
    )

    if auth_url_callback is not None:
        auth_url_callback(auth_url)
    if open_browser:
        webbrowser.open(auth_url)

    logger.bind(
        client_secret_path=str(client_secret_path),
        token_path=str(token_path),
        port=actual_port,
    ).info("Waiting for Gmail OAuth callback")
    try:
        server.handle_request()
    finally:
        server.server_close()

    if server.oauth_error:
        raise GmailError(f"Gmail OAuth failed: {server.oauth_error}")
    if not server.oauth_code:
        raise GmailError("Timed out waiting for Gmail OAuth callback")
    if server.oauth_state != state:
        raise GmailError("Gmail OAuth state mismatch")

    token_payload = _exchange_authorization_code(
        config=config,
        redirect_uri=redirect_uri,
        code=server.oauth_code,
        client=client,
    )
    token = _token_from_response(token_payload)
    _write_token(token_path=token_path, token=token)
    logger.bind(token_path=str(token_path)).success("Stored Gmail OAuth token")
    return GmailAuthResult(
        token_path=token_path,
        scope=token.scope or GMAIL_READONLY_SCOPE,
        expires_at=_format_expires_at(token.expires_at_epoch),
    )


def fetch_bulltard_recap_from_gmail(
    *,
    source_date: date,
    client_secret_path: Path = DEFAULT_GMAIL_CLIENT_SECRET_PATH,
    token_path: Path = DEFAULT_GMAIL_TOKEN_PATH,
    output_root: Path = DEFAULT_GMAIL_RECAP_CACHE_ROOT,
    query: str | None = None,
    max_results: int = 10,
    overwrite: bool = False,
    client: httpx.Client | None = None,
) -> GmailBulltardRecapResult:
    """Find the Bulltard recap email for one date and cache its body locally."""

    if max_results <= 0:
        raise GmailError("Gmail max results must be positive")

    active_client, owns_client = _active_client(client)
    try:
        access_token = _valid_access_token(
            client_secret_path=client_secret_path,
            token_path=token_path,
            client=active_client,
        )
        queries = (query,) if query else _default_bulltard_queries(source_date)
        seen_message_ids: set[str] = set()
        for query_text in queries:
            message_refs = _search_messages(
                query=query_text,
                max_results=max_results,
                access_token=access_token,
                client=active_client,
            )
            for message_ref in message_refs:
                message_id = str(message_ref.get("id", "")).strip()
                if not message_id or message_id in seen_message_ids:
                    continue
                seen_message_ids.add(message_id)
                message = _get_message(
                    message_id=message_id,
                    access_token=access_token,
                    client=active_client,
                )
                body = _message_body(message)
                if not body:
                    continue
                try:
                    signed_url = extract_signed_source_url(body)
                except SignedSourceUrlError:
                    continue

                recap_path = _write_recap_cache(
                    output_root=output_root,
                    source_date=source_date,
                    body=body,
                    overwrite=overwrite,
                )
                headers = _message_headers(message)
                result = GmailBulltardRecapResult(
                    source_date=source_date,
                    message_id=message_id,
                    thread_id=_optional_str(message.get("threadId")),
                    subject=headers.get("subject"),
                    sender=headers.get("from"),
                    received_at=headers.get("date") or _internal_date(message),
                    recap_path=recap_path,
                    signed_url=signed_url,
                    query=query_text,
                )
                logger.bind(
                    source_date=source_date.isoformat(),
                    message_id=message_id,
                    recap_path=str(recap_path),
                ).success("Fetched Bulltard recap from Gmail")
                return result

        raise GmailError(f"No Bulltard recap with a signed app link found for {source_date}")
    finally:
        if owns_client:
            active_client.close()


def _load_oauth_client_config(path: Path) -> _OAuthClientConfig:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GmailError(f"Failed to read Gmail OAuth client secret: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GmailError(f"Invalid Gmail OAuth client secret JSON: {path}") from exc

    config = payload.get("installed") or payload.get("web")
    if not isinstance(config, dict):
        raise GmailError("Gmail OAuth client secret must contain an installed or web client")

    client_id = _required_str(config, "client_id")
    client_secret = _optional_str(config.get("client_secret"))
    auth_uri = _optional_str(config.get("auth_uri")) or GOOGLE_AUTH_URI
    token_uri = _optional_str(config.get("token_uri")) or GOOGLE_TOKEN_URI
    return _OAuthClientConfig(
        client_id=client_id,
        client_secret=client_secret,
        auth_uri=auth_uri,
        token_uri=token_uri,
    )


def _build_authorization_url(
    *,
    config: _OAuthClientConfig,
    redirect_uri: str,
    state: str,
) -> str:
    return (
        config.auth_uri
        + "?"
        + urlencode(
            {
                "client_id": config.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": GMAIL_READONLY_SCOPE,
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }
        )
    )


def _exchange_authorization_code(
    *,
    config: _OAuthClientConfig,
    redirect_uri: str,
    code: str,
    client: httpx.Client | None,
) -> dict[str, Any]:
    active_client, owns_client = _active_client(client)
    try:
        data = {
            "client_id": config.client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        if config.client_secret:
            data["client_secret"] = config.client_secret
        response = active_client.post(config.token_uri, data=data)
        return _json_response(response, context="exchange Gmail OAuth code")
    finally:
        if owns_client:
            active_client.close()


def _valid_access_token(
    *,
    client_secret_path: Path,
    token_path: Path,
    client: httpx.Client,
) -> str:
    token = _read_token(token_path)
    if token.access_token and not _token_is_expired(token):
        return token.access_token

    if not token.refresh_token:
        raise GmailError("Gmail token is expired and does not contain a refresh token")

    config = _load_oauth_client_config(client_secret_path)
    data = {
        "client_id": config.client_id,
        "refresh_token": token.refresh_token,
        "grant_type": "refresh_token",
    }
    if config.client_secret:
        data["client_secret"] = config.client_secret
    response = client.post(config.token_uri, data=data)
    refreshed = _token_from_response(
        _json_response(response, context="refresh Gmail OAuth token"),
        fallback_refresh_token=token.refresh_token,
    )
    _write_token(token_path=token_path, token=refreshed)
    return refreshed.access_token


def _read_token(path: Path) -> _OAuthToken:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GmailError(f"Failed to read Gmail token: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GmailError(f"Invalid Gmail token JSON: {path}") from exc
    return _OAuthToken(
        access_token=_required_str(payload, "access_token"),
        refresh_token=_optional_str(payload.get("refresh_token")),
        scope=_optional_str(payload.get("scope")),
        token_type=_optional_str(payload.get("token_type")),
        expires_at_epoch=_optional_int(payload.get("expires_at_epoch")),
    )


def _write_token(*, token_path: Path, token: _OAuthToken) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
        "scope": token.scope,
        "token_type": token.token_type,
        "expires_at_epoch": token.expires_at_epoch,
    }
    try:
        token_path.write_text(
            json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise GmailError(f"Failed to write Gmail token: {token_path}") from exc
    try:
        token_path.chmod(0o600)
    except OSError:
        logger.bind(token_path=str(token_path)).warning("Could not restrict Gmail token file mode")


def _token_from_response(
    payload: dict[str, Any],
    *,
    fallback_refresh_token: str | None = None,
) -> _OAuthToken:
    expires_at_epoch = None
    expires_in = _optional_int(payload.get("expires_in"))
    if expires_in is not None:
        expires_at_epoch = int(time.time()) + expires_in - TOKEN_EXPIRY_SKEW_SECONDS
    return _OAuthToken(
        access_token=_required_str(payload, "access_token"),
        refresh_token=_optional_str(payload.get("refresh_token")) or fallback_refresh_token,
        scope=_optional_str(payload.get("scope")),
        token_type=_optional_str(payload.get("token_type")),
        expires_at_epoch=expires_at_epoch,
    )


def _token_is_expired(token: _OAuthToken) -> bool:
    return token.expires_at_epoch is None or token.expires_at_epoch <= int(time.time())


def _search_messages(
    *,
    query: str,
    max_results: int,
    access_token: str,
    client: httpx.Client,
) -> tuple[dict[str, Any], ...]:
    response = client.get(
        f"{GMAIL_API_ROOT}/users/me/messages",
        headers=_auth_headers(access_token),
        params={
            "q": query,
            "maxResults": max_results,
        },
    )
    payload = _json_response(response, context="search Gmail messages")
    messages = payload.get("messages", ())
    if messages is None:
        return ()
    if not isinstance(messages, list):
        raise GmailError("Gmail message search returned an invalid messages field")
    return tuple(message for message in messages if isinstance(message, dict))


def _get_message(
    *,
    message_id: str,
    access_token: str,
    client: httpx.Client,
) -> dict[str, Any]:
    response = client.get(
        f"{GMAIL_API_ROOT}/users/me/messages/{message_id}",
        headers=_auth_headers(access_token),
        params={"format": "full"},
    )
    payload = _json_response(response, context=f"fetch Gmail message {message_id}")
    if not isinstance(payload, dict):
        raise GmailError("Gmail message fetch returned an invalid payload")
    return payload


def _json_response(response: httpx.Response, *, context: str) -> dict[str, Any]:
    if response.status_code >= 400:
        detail = _response_error_detail(response)
        raise GmailError(f"Failed to {context}: HTTP {response.status_code} {detail}".strip())
    try:
        payload = response.json()
    except ValueError as exc:
        raise GmailError(f"Failed to decode JSON while trying to {context}") from exc
    if not isinstance(payload, dict):
        raise GmailError(f"Expected JSON object while trying to {context}")
    return payload


def _response_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:300]
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = error.get("message")
        return str(message) if message else ""
    return ""


def _message_body(message: dict[str, Any]) -> str:
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return ""
    html_parts, text_parts = _body_parts(payload)
    if html_parts:
        return "\n".join(html_parts)
    return "\n".join(text_parts)


def _body_parts(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    html_parts: list[str] = []
    text_parts: list[str] = []
    _collect_body_parts(payload, html_parts=html_parts, text_parts=text_parts)
    return html_parts, text_parts


def _collect_body_parts(
    payload: dict[str, Any],
    *,
    html_parts: list[str],
    text_parts: list[str],
) -> None:
    mime_type = str(payload.get("mimeType", "")).lower()
    body = payload.get("body")
    data = body.get("data") if isinstance(body, dict) else None
    if isinstance(data, str):
        decoded = _decode_base64url(data)
        if mime_type == "text/html":
            html_parts.append(decoded)
        elif mime_type == "text/plain":
            text_parts.append(decoded)

    parts = payload.get("parts", ())
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, dict):
                _collect_body_parts(part, html_parts=html_parts, text_parts=text_parts)


def _decode_base64url(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding).decode("utf-8", errors="replace")
    except (ValueError, OSError) as exc:
        raise GmailError("Failed to decode Gmail message body") from exc


def _message_headers(message: dict[str, Any]) -> dict[str, str]:
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return {}
    headers = payload.get("headers", ())
    if not isinstance(headers, list):
        return {}
    result: dict[str, str] = {}
    for header in headers:
        if not isinstance(header, dict):
            continue
        name = _optional_str(header.get("name"))
        value = _optional_str(header.get("value"))
        if name and value:
            result[name.lower()] = value
    return result


def _internal_date(message: dict[str, Any]) -> str | None:
    value = _optional_int(message.get("internalDate"))
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat(timespec="seconds")


def _write_recap_cache(
    *,
    output_root: Path,
    source_date: date,
    body: str,
    overwrite: bool,
) -> Path:
    path = output_root / f"recap-{source_date.isoformat()}.html"
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise GmailError(f"Failed to read existing recap cache: {path}") from exc
        if existing == body:
            return path
        if not overwrite:
            raise GmailError(
                f"Refusing to overwrite existing recap cache with different content: {path}"
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(body, encoding="utf-8")
    except OSError as exc:
        raise GmailError(f"Failed to write recap cache: {path}") from exc
    return path


def _default_bulltard_queries(source_date: date) -> tuple[str, ...]:
    after = source_date.strftime("%Y/%m/%d")
    before = (source_date + timedelta(days=1)).strftime("%Y/%m/%d")
    return (
        f"Bulltard after:{after} before:{before}",
        f"jamesbulltard after:{after} before:{before}",
        f"from:substack after:{after} before:{before} Bulltard",
    )


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _active_client(client: httpx.Client | None) -> tuple[httpx.Client, bool]:
    if client is not None:
        return client, False
    return httpx.Client(timeout=HTTP_TIMEOUT_SECONDS), True


def _format_expires_at(expires_at_epoch: int | None) -> str | None:
    if expires_at_epoch is None:
        return None
    return datetime.fromtimestamp(expires_at_epoch, tz=UTC).isoformat(timespec="seconds")


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = _optional_str(payload.get(key))
    if not value:
        raise GmailError(f"Missing required Gmail field: {key}")
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


class _OAuthCallbackServer(HTTPServer):
    oauth_code: str | None = None
    oauth_error: str | None = None
    oauth_state: str | None = None


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        params = parse_qs(urlsplit(self.path).query)
        self.server.oauth_code = _first_query_value(params, "code")
        self.server.oauth_error = _first_query_value(params, "error")
        self.server.oauth_state = _first_query_value(params, "state")
        body = (
            "<html><body><h1>MarketLab Gmail authorization complete.</h1>"
            "<p>You can close this window.</p></body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _first_query_value(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    if not values:
        return None
    return values[0]
