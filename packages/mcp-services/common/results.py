import uuid
from typing import Any


def success(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None, "trace_id": str(uuid.uuid4())}


def failure(
    code: str,
    message: str,
    *,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error = {"code": code, "message": message, "retryable": retryable}
    if details:
        error.update(details)
    return {
        "ok": False,
        "data": None,
        "error": error,
        "trace_id": str(uuid.uuid4()),
    }
