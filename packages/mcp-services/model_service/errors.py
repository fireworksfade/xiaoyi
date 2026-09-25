"""模型服务领域错误。

对外只暴露稳定错误码，不把 Python 堆栈返回给调用方。
"""

from __future__ import annotations

MODEL_CACHE_INCOMPLETE = "MODEL_CACHE_INCOMPLETE"
CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
MODEL_LOAD_FAILED = "MODEL_LOAD_FAILED"


class ModelServiceError(RuntimeError):
    """带稳定错误码的服务错误；HTTP 层据此返回 503 与公共错误结构。"""

    def __init__(self, code: str, message: str, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}
