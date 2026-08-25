"""Data contracts for Bulltard source captures."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Self

from marketlab.bulltard.redaction import redact_url


class CaptureStatus(StrEnum):
    """Outcome for one attempted capture artifact."""

    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class RawArtifact:
    """Metadata for one immutable raw payload captured from an authorized source."""

    route_name: str
    path: str
    source_url: str
    final_url: str
    status: CaptureStatus
    status_code: int | None
    content_type: str | None
    captured_at: datetime
    sha256: str
    byte_count: int

    def __post_init__(self) -> None:
        if not self.route_name:
            raise ValueError("route_name is required")
        if not self.path:
            raise ValueError("path is required")
        if not self.source_url:
            raise ValueError("source_url is required")
        if not self.final_url:
            raise ValueError("final_url is required")
        if self.byte_count < 0:
            raise ValueError("byte_count cannot be negative")
        if len(self.sha256) != 64:
            raise ValueError("sha256 must be a 64-character hex digest")
        try:
            int(self.sha256, 16)
        except ValueError as exc:
            raise ValueError("sha256 must be a 64-character hex digest") from exc
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")

    @classmethod
    def from_bytes(
        cls,
        *,
        route_name: str,
        path: str,
        source_url: str,
        final_url: str,
        payload: bytes,
        status_code: int,
        content_type: str | None,
        captured_at: datetime | None = None,
    ) -> Self:
        return cls(
            route_name=route_name,
            path=path,
            source_url=source_url,
            final_url=final_url,
            status=CaptureStatus.OK,
            status_code=status_code,
            content_type=content_type,
            captured_at=captured_at or datetime.now(UTC),
            sha256=hashlib.sha256(payload).hexdigest(),
            byte_count=len(payload),
        )

    def to_dict(self, *, redact_urls: bool = True) -> dict[str, Any]:
        return {
            "route_name": self.route_name,
            "path": self.path,
            "source_url": redact_url(self.source_url) if redact_urls else self.source_url,
            "final_url": redact_url(self.final_url) if redact_urls else self.final_url,
            "status": self.status.value,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "captured_at": self.captured_at.isoformat(),
            "sha256": self.sha256,
            "byte_count": self.byte_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            route_name=data["route_name"],
            path=data["path"],
            source_url=data["source_url"],
            final_url=data["final_url"],
            status=CaptureStatus(data["status"]),
            status_code=data["status_code"],
            content_type=data["content_type"],
            captured_at=datetime.fromisoformat(data["captured_at"]),
            sha256=data["sha256"],
            byte_count=data["byte_count"],
        )


@dataclass(frozen=True, slots=True)
class CaptureManifest:
    """Machine-readable summary for one Bulltard capture attempt."""

    source_date: date
    capture_version: str
    created_at: datetime
    artifacts: tuple[RawArtifact, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.capture_version:
            raise ValueError("capture_version is required")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")

    @property
    def is_partial(self) -> bool:
        return bool(self.errors) or any(
            artifact.status != CaptureStatus.OK for artifact in self.artifacts
        )

    def to_dict(self, *, redact_urls: bool = True) -> dict[str, Any]:
        return {
            "source": "bulltard",
            "source_date": self.source_date.isoformat(),
            "capture_version": self.capture_version,
            "created_at": self.created_at.isoformat(),
            "is_partial": self.is_partial,
            "artifacts": [artifact.to_dict(redact_urls=redact_urls) for artifact in self.artifacts],
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        if data.get("source") != "bulltard":
            raise ValueError("manifest source must be bulltard")
        return cls(
            source_date=date.fromisoformat(data["source_date"]),
            capture_version=data["capture_version"],
            created_at=datetime.fromisoformat(data["created_at"]),
            artifacts=tuple(RawArtifact.from_dict(item) for item in data["artifacts"]),
            errors=tuple(data["errors"]),
        )

    def to_json(self, *, redact_urls: bool = True) -> str:
        return json.dumps(self.to_dict(redact_urls=redact_urls), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Self:
        return cls.from_dict(json.loads(text))
