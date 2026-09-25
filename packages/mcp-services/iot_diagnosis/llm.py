from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMResponse:
    data: dict[str, Any]
    latency_ms: float
    input_tokens: int
    output_tokens: int


class DiagnosisLLMClient:
    def __init__(self, api_key: str, base_url: str, model: str, timeout_seconds: float = 20):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.model)

    @classmethod
    def from_env(cls) -> "DiagnosisLLMClient":
        return cls(
            os.getenv("DIAGNOSIS_LLM_API_KEY", ""),
            os.getenv("DIAGNOSIS_LLM_BASE_URL", "https://api.openai.com/v1"),
            os.getenv("DIAGNOSIS_LLM_MODEL", ""),
            float(os.getenv("DIAGNOSIS_LLM_TIMEOUT_SECONDS", "20")),
        )

    def _complete_json(self, system: str, user: dict[str, Any]) -> LLMResponse:
        if not self.available:
            raise LLMClientError("LLM_NOT_CONFIGURED")
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                ],
            }
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        started = time.perf_counter()
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise LLMClientError("LLM_REQUEST_FAILED") from exc
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        try:
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMClientError("LLM_RESPONSE_INVALID") from exc
        if not isinstance(parsed, dict):
            raise LLMClientError("LLM_RESPONSE_INVALID")
        usage = payload.get("usage") or {}
        return LLMResponse(
            data=parsed,
            latency_ms=latency_ms,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )

    def route(self, query: str, state: dict[str, Any] | None, logs: list[str]) -> LLMResponse:
        return self._complete_json(
            "你是 IoT 诊断检索路由器。只输出 JSON。根据问题选择必要知识源，禁止选择未知来源。",
            {
                "query": query,
                "device_state": state,
                "logs": logs[:10],
                "allowed_sources": [
                    "fault_cases",
                    "mqtt_docs",
                    "wifi_docs",
                    "sensor_docs",
                    "device_docs",
                    "realtime_db",
                ],
                "output_schema": {
                    "fault_type": "mqtt|wifi|sensor|device|unknown",
                    "need_retrieval": True,
                    "sources": ["source"],
                    "top_k": 5,
                },
            },
        )

    def diagnose(
        self,
        query: str,
        state: dict[str, Any],
        logs: list[str],
        contexts: list[dict[str, Any]],
    ) -> LLMResponse:
        return self._complete_json(
            "你是 IoT 故障诊断器。只依据输入证据输出 JSON；证据不足时明确要求人工检查。",
            {
                "query": query,
                "device_state": state,
                "logs": logs[:20],
                "contexts": contexts[:4],
                "output_schema": {
                    "fault_type": "string",
                    "fault_name": "string",
                    "cause": "string",
                    "solutions": ["string"],
                    "severity": "low|medium|high|critical",
                    "confidence": 0.0,
                    "requires_manual_inspection": False,
                },
            },
        )
