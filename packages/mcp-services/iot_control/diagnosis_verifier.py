"""通过 Diagnosis 服务验证修复动作所引用的诊断记录。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class DiagnosisVerificationError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class DiagnosisVerifier:
    url: str
    bearer_token: str = ""
    timeout_seconds: float = 3.0

    @classmethod
    def from_environment(cls) -> "DiagnosisVerifier":
        return cls(
            url=os.getenv(
                "CONTROL_DIAGNOSIS_VERIFY_URL",
                "http://127.0.0.1:9001/internal/diagnoses/verify",
            ),
            bearer_token=os.getenv(
                "CONTROL_DIAGNOSIS_VERIFY_TOKEN",
                os.getenv("CONTROL_MCP_BEARER_TOKEN", ""),
            ).strip(),
            timeout_seconds=max(
                0.1, float(os.getenv("CONTROL_DIAGNOSIS_VERIFY_TIMEOUT_SECONDS", "3"))
            ),
        )

    def verify(self, diagnosis_id: str, device_id: str) -> dict[str, Any]:
        body = json.dumps(
            {"diagnosis_id": diagnosis_id, "device_id": device_id}, ensure_ascii=False
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        request = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = {}
            error = payload.get("error") if isinstance(payload, dict) else None
            code = error.get("code") if isinstance(error, dict) else "DIAGNOSIS_VERIFY_FAILED"
            message = error.get("message") if isinstance(error, dict) else "诊断关联验证失败"
            raise DiagnosisVerificationError(str(code), str(message)) from exc
        except (OSError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DiagnosisVerificationError(
                "DIAGNOSIS_VERIFY_UNAVAILABLE",
                "诊断服务暂时不可用，未执行修复动作",
                retryable=True,
            ) from exc

        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise DiagnosisVerificationError(
                "DIAGNOSIS_VERIFY_INVALID_RESPONSE",
                "诊断服务返回了无效的验证结果",
                retryable=True,
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise DiagnosisVerificationError(
                "DIAGNOSIS_VERIFY_INVALID_RESPONSE",
                "诊断服务返回了无效的验证结果",
                retryable=True,
            )
        return data
