"""结构化 JSON 日志（specs WP-12 / §11.2）。

统一字段：timestamp / level / service / event / request_id / run_id / trace_id /
device_id（存在时）/ duration_ms / error_code。公共错误结构对客户端保持稳定，
内部堆栈只进日志。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

# 业务通过 extra= 传递的关联字段白名单
CONTEXT_FIELDS = (
    "request_id",
    "run_id",
    "trace_id",
    "device_id",
    "duration_ms",
    "error_code",
)


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "event": record.getMessage(),
        }
        for field in CONTEXT_FIELDS:
            value = record.__dict__.get(field)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(service: str = "xiaoyi-backend", level: int = logging.INFO) -> None:
    """挂载 JSON handler 到 root logger（幂等，供应用与 CLI 共用）。"""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
