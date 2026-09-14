"""结构化日志与错误分类测试（specs WP-12 / §11.2、§11.4、§16.4）。"""

import json
import logging

from app.errors import ERROR_CLASSES, AppError, classify
from app.observability.logging import JsonFormatter, configure_logging


def test_json_formatter_emits_context_fields() -> None:
    formatter = JsonFormatter("xiaoyi-backend")
    record = logging.LogRecord(
        name="xiaoyi.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="run failed",
        args=(),
        exc_info=None,
    )
    record.run_id = "RUN-1"
    record.request_id = "REQ-1"
    record.error_code = "RUN_INTERRUPTED"
    record.duration_ms = 12.5

    payload = json.loads(formatter.format(record))

    assert payload["service"] == "xiaoyi-backend"
    assert payload["level"] == "WARNING"
    assert payload["event"] == "run failed"
    assert payload["run_id"] == "RUN-1"
    assert payload["request_id"] == "REQ-1"
    assert payload["error_code"] == "RUN_INTERRUPTED"
    assert payload["duration_ms"] == 12.5
    assert "timestamp" in payload


def test_json_formatter_includes_exception_stack() -> None:
    formatter = JsonFormatter("xiaoyi-backend")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        import sys

        record = logging.LogRecord(
            name="xiaoyi.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="agent run failed",
            args=(),
            exc_info=sys.exc_info(),
        )
    payload = json.loads(formatter.format(record))
    assert "RuntimeError: boom" in payload["exc_info"]


def test_configure_logging_installs_json_handler() -> None:
    configure_logging("xiaoyi-test")
    root = logging.getLogger()
    try:
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
        assert root.handlers[0].formatter.service == "xiaoyi-test"
    finally:
        root.handlers = []


def test_error_taxonomy_retryability_matches_spec() -> None:
    # 任务中断可由用户重试；配置/校验/schema 不兼容不可重试
    assert ERROR_CLASSES["RUN_INTERRUPTED"].retryable is True
    assert ERROR_CLASSES["CONFIGURATION_ERROR"].retryable is False
    assert ERROR_CLASSES["VALIDATION_ERROR"].retryable is False
    assert ERROR_CLASSES["DATABASE_SCHEMA_AHEAD"].retryable is False
    assert ERROR_CLASSES["DATABASE_SCHEMA_BEHIND"].retryable is False
    # 外部依赖暂时不可用可重试
    assert ERROR_CLASSES["DEPENDENCY_UNAVAILABLE"].retryable is True
    assert ERROR_CLASSES["MODEL_CACHE_INCOMPLETE"].http_status == 503


def test_unknown_code_falls_back_to_stable_public_error() -> None:
    fallback = classify("TOTALLY_UNKNOWN")
    assert fallback.code == "AGENT_RUN_FAILED"
    assert fallback.retryable is False

    error = AppError("DATABASE_SCHEMA_AHEAD")
    assert error.code == "DATABASE_SCHEMA_AHEAD"
    assert error.error_class.http_status == 503
