"""Natural-language analytics over a small, read-only IoT schema.

The model sees only scoped temporary views. SQLite's authorizer enforces that
boundary even if generated SQL ignores the prompt or references physical tables.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from iot_diagnosis.llm import DiagnosisLLMClient, LLMClientError
from iot_diagnosis.query_plan import PLAN_CONTRACT, QueryPlanError, compile_plan
from iot_diagnosis.repository import DiagnosisRepository

SCHEMA = {
    "iot_devices": "device_id, device_type, name, firmware_version, created_at, updated_at",
    "iot_state": (
        "device_id, online (effective: reported online AND fresh heartbeat), reported_online, "
        "heartbeat_fresh, wifi_status, rssi (dBm), mqtt_status, temperature (C), uptime (seconds), "
        "device_timestamp, received_at, last_event_kind"
    ),
    "iot_telemetry": (
        "id, device_id, temperature (C), rssi (dBm), uptime (seconds), wifi_status, "
        "mqtt_status, device_timestamp, received_at"
    ),
    "iot_logs": "id, device_id, level, module, message, timestamp",
    "iot_diagnoses": (
        "diagnosis_id, device_id, query, fault_type, fault_name, cause, confidence, error, created_at"
    ),
}
_BASE_TABLES = {
    "iot_devices": "device",
    "iot_state": "device_current_state",
    "iot_telemetry": "device_telemetry",
    "iot_logs": "device_log",
    "iot_diagnoses": "diagnosis_record",
}
_FUNCTIONS = frozenset(
    "abs avg count sum total min max round coalesce ifnull nullif lower upper substr substring "
    "instr length replace trim ltrim rtrim date time datetime julianday strftime unixepoch "
    "timediff like glob row_number rank dense_rank lag lead first_value last_value".split()
)
MAX_RESULT_BYTES = 32_000


class Text2SQLError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _literal(db: sqlite3.Connection, value: Any) -> str:
    # Let SQLite quote trusted view definitions, including an optional device scope.
    return str(db.execute("SELECT quote(?)", (value,)).fetchone()[0])


def _create_views(
    db: sqlite3.Connection, device_id: str | None, now: datetime, offline_after_seconds: int
) -> dict[str, str]:
    scope = (
        " WHERE device_id IS NOT NULL"
        if device_id is None
        else f" WHERE device_id = {_literal(db, device_id)}"
    )
    now_sql = _literal(db, now.isoformat())
    fresh = (
        f"COALESCE((julianday({now_sql}) - julianday(received_at)) * 86400 "
        f"<= {max(1, int(offline_after_seconds))}, 0)"
    )
    selections = {
        "iot_devices": "device_id, device_type, name, firmware_version, created_at, updated_at",
        "iot_state": (
            f"device_id, (online != 0 AND {fresh}) AS online, online AS reported_online, "
            f"{fresh} AS heartbeat_fresh, wifi_status, rssi, mqtt_status, temperature, uptime, "
            "device_timestamp, received_at, last_event_kind"
        ),
        "iot_telemetry": (
            "id, device_id, temperature, rssi, uptime, wifi_status, mqtt_status, "
            "device_timestamp, received_at"
        ),
        "iot_logs": "id, device_id, level, module, message, timestamp",
        "iot_diagnoses": (
            "diagnosis_id, device_id, query, fault_type, fault_name, cause, confidence, error, created_at"
        ),
    }
    private_views = {}
    for view, columns in selections.items():
        # Authorizer's source is also a CTE name. Use unpredictable private view
        # names so a model-authored CTE cannot impersonate an authorized source.
        private = f"_scope_{uuid.uuid4().hex}"
        private_views[private] = view
        db.execute(
            f"CREATE TEMP VIEW {private} AS SELECT {columns} FROM main.{_BASE_TABLES[view]}{scope}"
        )
        db.execute(f"CREATE TEMP VIEW {view} AS SELECT * FROM temp.{private}")
    return private_views


def execute_readonly(
    repository: DiagnosisRepository,
    sql: str,
    parameters: dict[str, Any],
    *,
    device_id: str | None = None,
    max_rows: int = 100,
    now: datetime | None = None,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    """Execute one SELECT/CTE; reject direct base-table access and all other operations."""
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 12_000:
        raise Text2SQLError("SQL_QUERY_INVALID", "SQL 必须是长度不超过 12000 的查询")
    if not re.match(r"(?:SELECT|WITH)\b", sql.lstrip(), re.IGNORECASE):
        raise Text2SQLError("SQL_QUERY_REJECTED", "只允许 SELECT 或 WITH SELECT 查询")
    if not 1 <= max_rows <= 200 or not 0 < timeout_seconds <= 5:
        raise Text2SQLError("INVALID_REQUEST", "查询上限无效")
    if device_id is not None and (
        not isinstance(device_id, str) or not 1 <= len(device_id) <= 120 or "\x00" in device_id
    ):
        raise Text2SQLError("INVALID_REQUEST", "设备范围无效")
    if not isinstance(parameters, dict) or len(parameters) > 50:
        raise Text2SQLError("SQL_QUERY_INVALID", "SQL 参数必须是对象，且最多 50 项")
    for key, value in parameters.items():
        if (
            not isinstance(key, str)
            or len(key) > 120
            or not (value is None or isinstance(value, (str, int, float)))
        ):
            raise Text2SQLError("SQL_QUERY_INVALID", "SQL 参数仅支持标量")
        if isinstance(value, str) and len(value) > 2000:
            raise Text2SQLError("SQL_QUERY_INVALID", "SQL 参数过长")
        if isinstance(value, float) and not math.isfinite(value):
            raise Text2SQLError("SQL_QUERY_INVALID", "SQL 参数必须是有限数值")
        if isinstance(value, int) and not -(2**63) <= value < 2**63:
            raise Text2SQLError("SQL_QUERY_INVALID", "SQL 整数参数超出范围")

    now = now or datetime.now(timezone.utc)
    sql = sql.strip().removesuffix(";").rstrip()
    executed_sql = sql
    views_read: set[str] = set()
    denied = False
    timed_out = False
    private_views: dict[str, str] = {}

    def authorize(action, arg1, arg2, database, source):
        nonlocal denied
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            # SQLite reports synthetic CTE reads without a database name.
            # Reads of their underlying physical tables are authorized separately.
            if database is None:
                return sqlite3.SQLITE_OK
            if database == "temp" and arg1 in SCHEMA:
                views_read.add(arg1)
                return sqlite3.SQLITE_OK
            if database == "temp" and arg1 in private_views and source == private_views[arg1]:
                return sqlite3.SQLITE_OK
            if (
                database == "main"
                and source in private_views
                and arg1 == _BASE_TABLES[private_views[source]]
            ):
                views_read.add(private_views[source])
                return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and str(arg2).lower() in _FUNCTIONS:
            return sqlite3.SQLITE_OK
        denied = True
        return sqlite3.SQLITE_DENY

    deadline = time.monotonic() + timeout_seconds

    def progress():
        nonlocal timed_out
        timed_out = time.monotonic() >= deadline
        return int(timed_out)

    started = time.perf_counter()
    try:
        uri = Path(repository.path).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=min(timeout_seconds, 1))) as db:
            private_views = _create_views(db, device_id, now, repository.offline_after_seconds)
            db.execute("PRAGMA query_only = ON")
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
            db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 13_000)
            db.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 50)
            db.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 10)
            db.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 50)
            db.set_authorizer(authorize)
            db.set_progress_handler(progress, 1000)
            # execute() accepts exactly one statement. The default-deny authorizer
            # permits only SELECT operations; cursor iteration caps output rows.
            cursor = db.execute(executed_sql, parameters)
            if not views_read:
                raise Text2SQLError("SQL_QUERY_REJECTED", "查询必须读取获准的 IoT 视图")
            columns = [column[0] for column in cursor.description]
            if len(columns) != len(set(columns)):
                raise Text2SQLError("SQL_QUERY_INVALID", "结果列名重复，请为列设置唯一别名")
            rows: list[dict[str, Any]] = []
            truncated = False
            cells_truncated = False
            result_bytes = 0
            for raw in cursor:
                if len(rows) >= max_rows:
                    truncated = True
                    break
                row = dict(zip(columns, raw, strict=True))
                for key, value in row.items():
                    if isinstance(value, bytes):
                        raise Text2SQLError("SQL_QUERY_INVALID", "查询结果不支持二进制值")
                    if isinstance(value, str) and len(value) > 2000:
                        row[key] = value[:2000]
                        cells_truncated = True
                    if isinstance(value, float) and not math.isfinite(value):
                        raise Text2SQLError("SQL_QUERY_INVALID", "查询产生了非有限数值")
                size = len(json.dumps(row, ensure_ascii=False).encode("utf-8"))
                if result_bytes + size > MAX_RESULT_BYTES:
                    truncated = True
                    break
                rows.append(row)
                result_bytes += size
    except sqlite3.Error as exc:
        if denied:
            raise Text2SQLError("SQL_QUERY_REJECTED", "SQL 包含未授权的数据源、函数或操作") from exc
        if timed_out:
            raise Text2SQLError("SQL_QUERY_TIMEOUT", "SQL 查询超过执行时间限制") from exc
        if isinstance(exc, sqlite3.OperationalError) and (
            "locked" in str(exc) or "unable to open" in str(exc)
        ):
            raise Text2SQLError("SQL_DATABASE_UNAVAILABLE", "IoT 数据库暂不可查询") from exc
        raise Text2SQLError("SQL_QUERY_INVALID", str(exc)) from exc
    return {
        "sql": sql,
        "executed_sql": executed_sql,
        "parameters": parameters,
        "columns": columns,
        "rows": rows,
        "returned": len(rows),
        "truncated": truncated,
        "cells_truncated": cells_truncated,
        "max_rows": max_rows,
        "sources": sorted(views_read),
        "device_id": device_id,
        "queried_at": now.isoformat(),
        "execution_latency_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def query_iot_data(
    repository: DiagnosisRepository,
    query: str,
    device_id: str | None = None,
    max_rows: int = 100,
    utc_offset_minutes: int = 480,
    *,
    llm_client: DiagnosisLLMClient | None = None,
) -> dict[str, Any]:
    """Validate the model's query plan and compile SQL with server-owned rules."""
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 2000:
        raise Text2SQLError("INVALID_REQUEST", "问题长度必须在 1–2000 之间")
    if not -720 <= utc_offset_minutes <= 840 or not 1 <= max_rows <= 200:
        raise Text2SQLError("INVALID_REQUEST", "时区或结果上限无效")
    if device_id is not None and (
        not isinstance(device_id, str) or not 1 <= len(device_id) <= 120 or "\x00" in device_id
    ):
        raise Text2SQLError("INVALID_REQUEST", "设备范围无效")
    # With no canonical disconnect event ID, counting matching log rows would
    # invent an event count. Explicit requests for matching log entries are valid.
    normalized = query.lower().replace(" ", "")
    if (
        any(word in normalized for word in ("掉线", "断线", "断开", "disconnect"))
        and any(
            word in normalized
            for word in (
                "次数",
                "几次",
                "多少次",
                "数量",
                "总数",
                "频率",
                "count",
                "frequency",
                "howmany",
                "numberof",
            )
        )
        and not any(
            word in normalized
            for word in ("日志条数", "日志数量", "几条", "多少条", "logentries", "logrecords")
        )
    ):
        raise Text2SQLError(
            "TEXT2SQL_CLARIFICATION_REQUIRED",
            "当前没有统一的掉线事件编号，无法可靠统计掉线次数。是否改为统计匹配的掉线日志条数，或提供事件去重口径？",
        )
    client = llm_client or DiagnosisLLMClient.from_env()
    if not client.available:
        raise Text2SQLError("LLM_NOT_CONFIGURED", "Text2SQL 需要配置 DIAGNOSIS_LLM_MODEL/API_KEY")
    now = datetime.now(timezone.utc)
    clock_parameters = {"now_utc": now.isoformat()}
    error_context = None
    llm_latency_ms = 0.0
    input_tokens = output_tokens = 0
    for attempt in range(2):
        try:
            response = client.text2sql(
                query, PLAN_CONTRACT, device_id, clock_parameters, utc_offset_minutes, error_context
            )
        except LLMClientError as exc:
            if str(exc) == "LLM_RESPONSE_INVALID" and attempt == 0:
                error_context = {
                    "error": "响应必须是一个合法 JSON 对象，仅包含 plan 和 clarification；禁止 Markdown 或解释文本。"
                }
                continue
            raise Text2SQLError(str(exc), "Text2SQL 模型请求失败，未执行查询") from exc
        llm_latency_ms += response.latency_ms
        input_tokens += response.input_tokens
        output_tokens += response.output_tokens
        data = response.data
        clarification = data.get("clarification")
        if isinstance(clarification, str) and clarification.strip():
            raise Text2SQLError("TEXT2SQL_CLARIFICATION_REQUIRED", clarification[:1000])
        try:
            if set(data) - {"plan", "clarification"}:
                raise QueryPlanError("模型只能返回 plan 和 clarification，禁止自由 SQL 或参数")
            if clarification is not None and not isinstance(clarification, str):
                raise QueryPlanError("clarification 必须是字符串或 null")
            compiled = compile_plan(
                data.get("plan"),
                device_id=device_id,
                now=now,
                utc_offset_minutes=utc_offset_minutes,
                max_rows=max_rows,
            )
        except QueryPlanError as exc:
            if attempt == 0 and exc.code == "TEXT2SQL_PLAN_INVALID":
                error_context = {"error": str(exc)[:1000]}
                continue
            raise Text2SQLError(exc.code, str(exc)) from exc
        # Compiler/database errors are service defects, never opportunities for
        # the model to bypass the plan contract with a raw SQL fallback.
        result = execute_readonly(
            repository,
            compiled.sql,
            compiled.parameters,
            device_id=compiled.device_id,
            max_rows=compiled.limit,
            now=now,
        )
        return {
            **result,
            "query": query,
            "utc_offset_minutes": utc_offset_minutes,
            "execution_mode": "query_plan",
            "query_plan": compiled.plan,
            "metric_definition": compiled.metric_definition,
            "time_window": compiled.time_window,
            "generation_attempts": attempt + 1,
            "llm_latency_ms": round(llm_latency_ms, 3),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
    raise AssertionError("unreachable")
