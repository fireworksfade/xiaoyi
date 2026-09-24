"""错误分类（specs WP-12 / §11.4、§16.4）。

每类错误有稳定的错误码、HTTP 状态、公开 message、retryable 与日志级别；
对外只暴露稳定的公共错误结构，内部堆栈保留在日志与事件数据中。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorClass:
    code: str
    http_status: int
    public_message: str
    retryable: bool
    log_level: str


ERROR_CLASSES: dict[str, ErrorClass] = {
    # 配置错误：不可重试，需要运维介入
    "CONFIGURATION_ERROR": ErrorClass("CONFIGURATION_ERROR", 500, "服务配置错误", False, "error"),
    # 参数/业务状态错误：不可自动重试
    "VALIDATION_ERROR": ErrorClass("VALIDATION_ERROR", 422, "请求参数无效", False, "info"),
    "CONTEXT_INPUT_TOO_LARGE": ErrorClass(
        "CONTEXT_INPUT_TOO_LARGE", 422, "输入内容超过上下文预算", False, "info"
    ),
    # 外部服务暂时不可用：可重试
    "DEPENDENCY_UNAVAILABLE": ErrorClass(
        "DEPENDENCY_UNAVAILABLE", 503, "依赖服务暂时不可用", True, "warning"
    ),
    # 任务中断：可由用户重试
    "RUN_INTERRUPTED": ErrorClass("RUN_INTERRUPTED", 409, "运行被取消，可重试", True, "warning"),
    "RUN_STOPPED": ErrorClass("RUN_STOPPED", 409, "用户已停止运行", True, "info"),
    # 数据库 schema 不兼容：运维处理后重试
    "DATABASE_SCHEMA_BEHIND": ErrorClass(
        "DATABASE_SCHEMA_BEHIND", 503, "数据库版本落后，请先执行迁移", False, "error"
    ),
    "DATABASE_SCHEMA_AHEAD": ErrorClass(
        "DATABASE_SCHEMA_AHEAD", 503, "数据库版本高于当前代码支持版本", False, "error"
    ),
    "MODEL_CACHE_INCOMPLETE": ErrorClass(
        "MODEL_CACHE_INCOMPLETE", 503, "模型缓存不完整", False, "error"
    ),
}

# 其余未知错误的兜底分类
FALLBACK_ERROR_CLASS = ErrorClass("AGENT_RUN_FAILED", 500, "小yi 运行失败", False, "error")


def classify(code: str | None) -> ErrorClass:
    if code is None:
        return FALLBACK_ERROR_CLASS
    return ERROR_CLASSES.get(code, FALLBACK_ERROR_CLASS)


class AppError(Exception):
    """携带稳定错误码的业务异常；HTTP 层据此返回公共错误结构。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.error_class = classify(code)
        super().__init__(message or self.error_class.public_message)

    @property
    def code(self) -> str:
        return self.error_class.code
