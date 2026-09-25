"""Redacted, content-addressed local artifacts for recoverable run context."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RunArtifact, new_id, utc_now

REDACTION_VERSION = "v1"
SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "cookie",
    "set-cookie",
    "session",
    "session_token",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "credential",
    "token",
    "client_secret",
    "x-api-key",
}
BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
INLINE_SECRET_PATTERN = re.compile(
    r"(?i)\b(authorization|cookie|set-cookie|api[_-]?key|session[_-]?token|"
    r"access[_-]?token|refresh[_-]?token|password|client[_-]?secret)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


def _sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return normalized in {re.sub(r"[^a-z0-9]", "", item) for item in SENSITIVE_KEYS}


def sanitize_artifact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _sensitive_key(str(key)) else sanitize_artifact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_artifact(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_artifact(item) for item in value]
    if isinstance(value, str):
        redacted = BEARER_PATTERN.sub("Bearer [REDACTED]", value)
        return INLINE_SECRET_PATTERN.sub(r"\1\2[REDACTED]", redacted)
    return value


class LocalArtifactStore:
    def __init__(self, root: str | Path, retention_hours: int = 168) -> None:
        self.root = Path(root).expanduser().resolve()
        self.retention_hours = max(1, retention_hours)

    def _path(self, run_id: str, artifact_id: str) -> Path:
        # Neither segment is accepted from users. Keep a defensive resolve check anyway.
        safe_run = re.sub(r"[^A-Za-z0-9_-]", "_", run_id)
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", artifact_id)
        path = (self.root / safe_run / f"{safe_id}.json").resolve()
        if self.root != path and self.root not in path.parents:
            raise ValueError("ARTIFACT_PATH_OUTSIDE_ROOT")
        return path

    async def write(
        self,
        db: AsyncSession,
        *,
        run_id: str,
        kind: str,
        content: Any,
        content_type: str = "application/json",
    ) -> RunArtifact:
        sanitized = sanitize_artifact(content)
        if content_type == "application/json":
            raw = json.dumps(sanitized, ensure_ascii=False, default=str).encode("utf-8")
        else:
            raw = str(sanitized).encode("utf-8")
        artifact_id = new_id()
        path = self._path(run_id, artifact_id)

        def persist() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)

        await asyncio.to_thread(persist)
        now = utc_now()
        artifact = RunArtifact(
            id=artifact_id,
            run_id=run_id,
            kind=kind,
            storage_uri=str(path),
            content_type=content_type,
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            redaction_version=REDACTION_VERSION,
            created_at=now,
            expires_at=now + timedelta(hours=self.retention_hours),
        )
        db.add(artifact)
        return artifact

    async def read(self, artifact: RunArtifact) -> bytes:
        path = Path(artifact.storage_uri).resolve()
        if self.root != path and self.root not in path.parents:
            raise ValueError("ARTIFACT_PATH_OUTSIDE_ROOT")
        raw = await asyncio.to_thread(path.read_bytes)
        if hashlib.sha256(raw).hexdigest() != artifact.sha256:
            raise ValueError("ARTIFACT_INTEGRITY_FAILED")
        return raw


CRITICAL_FIELDS = (
    "ok",
    "device_id",
    "diagnosis_id",
    "proposal_id",
    "command_id",
    "case_id",
    "command_status",
    "status",
    "verify_status",
    "case_status",
    "risk_level",
    "fault_type",
    "confidence",
    "action",
)


def extract_critical_fields(value: Any) -> dict[str, Any]:
    found: dict[str, Any] = {}

    if isinstance(value, dict):
        nested = value.get("data")
        data = nested if isinstance(nested, dict) else value
        command_value = data.get("command")
        command = command_value if isinstance(command_value, dict) else None
        if command is not None and isinstance(command.get("status"), str):
            found["command_status"] = command["status"]

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if (
                    key in CRITICAL_FIELDS
                    and key not in found
                    and isinstance(child, (str, int, float, bool, type(None)))
                ):
                    found[key] = child
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return found
