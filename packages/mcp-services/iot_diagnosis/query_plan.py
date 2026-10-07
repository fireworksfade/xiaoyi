"""Validated analytics plans compiled exclusively from server-owned SQL fragments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MetricName = Literal[
    "temperature",
    "rssi",
    "uptime",
    "telemetry_samples",
    "telemetry_devices",
    "log_entries",
    "log_devices",
    "diagnosis_records",
    "diagnosed_devices",
    "devices",
    "online_devices",
    "offline_devices",
]
Aggregation = Literal["avg", "min", "max", "count"]
Dimension = Literal[
    "device_id", "device_type", "firmware_version", "module", "level", "fault_type", "error"
]


class QueryPlanError(ValueError):
    def __init__(self, message: str, *, clarification: bool = False):
        super().__init__(message)
        self.code = "TEXT2SQL_CLARIFICATION_REQUIRED" if clarification else "TEXT2SQL_PLAN_INVALID"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TimeWindow(StrictModel):
    kind: Literal["last_hours", "today", "yesterday", "range", "all", "current"]
    hours: int | None = Field(default=None, ge=1, le=4320)
    start: str | None = Field(default=None, min_length=1, max_length=64)
    end: str | None = Field(default=None, min_length=1, max_length=64)


class Filters(StrictModel):
    device_type: str | None = Field(default=None, min_length=1, max_length=120)
    firmware_version: str | None = Field(default=None, min_length=1, max_length=120)
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None
    module: str | None = Field(default=None, min_length=1, max_length=120)
    message_contains: str | None = Field(default=None, min_length=1, max_length=200)
    fault_type: str | None = Field(default=None, min_length=1, max_length=120)
    diagnosis_status: Literal["all", "succeeded", "failed"] = "all"
    value_min: float | None = Field(default=None, allow_inf_nan=False)
    value_max: float | None = Field(default=None, allow_inf_nan=False)


class Sort(StrictModel):
    key: Literal["avg", "min", "max", "count", "time", "device_id"]
    direction: Literal["asc", "desc"] = "desc"


class QueryPlan(StrictModel):
    metric: MetricName
    mode: Literal["aggregate", "details"] = "aggregate"
    aggregations: list[Aggregation] = Field(min_length=0, max_length=4)
    window: TimeWindow
    device_id: str | None = Field(default=None, min_length=1, max_length=120)
    bucket: Literal["none", "hour", "day"] = "none"
    group_by: list[Dimension] = Field(default_factory=list, max_length=4)
    filters: Filters = Field(default_factory=Filters)
    sort: Sort | None = None
    limit: int = Field(default=100, ge=1, le=200)


METRIC_CATALOG: dict[str, dict[str, str]] = {
    "temperature": {"unit": "°C", "definition": "历史遥测温度；聚合按有效测量样本计算"},
    "rssi": {"unit": "dBm", "definition": "历史遥测信号强度；聚合按有效测量样本计算"},
    "uptime": {"unit": "seconds", "definition": "遥测上报的累计运行时长；不是窗口内新增运行时间"},
    "telemetry_samples": {"unit": "records", "definition": "遥测记录条数，不是设备数或故障事件数"},
    "telemetry_devices": {"unit": "devices", "definition": "窗口内有遥测记录的去重设备数量"},
    "log_devices": {
        "unit": "devices",
        "definition": "窗口内有匹配日志的去重设备数量，不是日志条数",
    },
    "diagnosed_devices": {"unit": "devices", "definition": "窗口内有匹配诊断记录的去重设备数量"},
    "log_entries": {
        "unit": "records",
        "definition": "匹配日志的条数，不是掉线、重启等真实事件次数",
    },
    "diagnosis_records": {
        "unit": "records",
        "definition": "历史模型诊断记录条数，不是已验证故障数",
    },
    "devices": {"unit": "devices", "definition": "当前已登记设备数量；不支持历史设备数量"},
    "online_devices": {"unit": "devices", "definition": "当前上报在线且心跳未过期的设备数量"},
    "offline_devices": {"unit": "devices", "definition": "当前离线、心跳过期或尚无状态的设备数量"},
}
PLAN_CONTRACT = {"metrics": METRIC_CATALOG, "plan_schema": QueryPlan.model_json_schema()}
_NUMERIC = frozenset({"temperature", "rssi", "uptime"})
_INVENTORY = frozenset({"devices", "online_devices", "offline_devices"})
_DISTINCT_DEVICES = frozenset({"telemetry_devices", "log_devices", "diagnosed_devices"})
_SOURCE = {
    **dict.fromkeys([*_NUMERIC, "telemetry_samples", "telemetry_devices"], "iot_telemetry"),
    "log_entries": "iot_logs",
    "log_devices": "iot_logs",
    "diagnosis_records": "iot_diagnoses",
    "diagnosed_devices": "iot_diagnoses",
    **dict.fromkeys(_INVENTORY, "iot_devices"),
}
_TIME = {"iot_telemetry": "received_at", "iot_logs": "timestamp", "iot_diagnoses": "created_at"}


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    parameters: dict[str, Any]
    device_id: str | None
    limit: int
    plan: dict[str, Any]
    metric_definition: dict[str, str]
    time_window: dict[str, Any]


def _window(window: TimeWindow, now: datetime, offset: int) -> dict[str, Any]:
    extra = window.model_dump(exclude_none=True)
    expected = {"kind"}
    if window.kind == "last_hours":
        expected.add("hours")
    elif window.kind == "range":
        expected.update({"start", "end"})
    if set(extra) != expected:
        raise QueryPlanError("时间窗口参数不完整或含不适用字段")
    if window.kind == "current":
        return {"kind": "current", "start_utc": None, "end_utc": None}
    if window.kind == "all":
        return {
            "kind": "all",
            "start_utc": None,
            "end_utc": now.isoformat(),
            "bounds": "(-inf, end)",
        }
    local_tz = timezone(timedelta(minutes=offset))
    if window.kind == "last_hours":
        assert window.hours is not None
        start, end = now - timedelta(hours=window.hours), now
    elif window.kind in ("today", "yesterday"):
        midnight = now.astimezone(local_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        start = midnight if window.kind == "today" else midnight - timedelta(days=1)
        end = now if window.kind == "today" else midnight
        start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    else:
        try:
            start = datetime.fromisoformat(str(window.start).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(window.end).replace("Z", "+00:00"))
        except ValueError as exc:
            raise QueryPlanError("时间范围必须使用 ISO 日期或时间") from exc
        start = start.replace(tzinfo=local_tz) if start.tzinfo is None else start
        end = end.replace(tzinfo=local_tz) if end.tzinfo is None else end
        start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        if start >= end:
            raise QueryPlanError("时间范围起点必须早于终点")
        if end > now:
            raise QueryPlanError(
                "历史查询的终点不能晚于当前时间，请明确历史范围", clarification=True
            )
    if start >= end or end - start > timedelta(days=366):
        raise QueryPlanError("历史查询窗口必须为正且不超过 366 天")
    return {
        "kind": window.kind,
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "bounds": "[start, end)",
    }


def compile_plan(
    raw: Any, *, device_id: str | None, now: datetime, utc_offset_minutes: int, max_rows: int
) -> CompiledQuery:
    if not -720 <= utc_offset_minutes <= 840 or not 1 <= max_rows <= 200:
        raise QueryPlanError("时区或结果上限无效")
    try:
        plan = QueryPlan.model_validate(raw)
    except ValidationError as exc:
        # Changing an unsupported metric or a sum into a different supported
        # question would silently alter the business meaning during correction.
        if (
            isinstance(raw, dict)
            and isinstance(raw.get("metric"), str)
            and raw["metric"] not in METRIC_CATALOG
        ):
            raise QueryPlanError(
                "指标目录不支持该指标，请明确所需口径或改查已支持指标", clarification=True
            ) from exc
        if (
            isinstance(raw, dict)
            and isinstance(raw.get("aggregations"), list)
            and "sum" in raw["aggregations"]
        ):
            raise QueryPlanError(
                "该查询计划不支持求和，累计 uptime 等指标不能直接相加；请明确统计口径",
                clarification=True,
            ) from exc
        raise QueryPlanError(str(exc)[:1200]) from exc
    if plan.device_id is not None and "\x00" in plan.device_id:
        raise QueryPlanError("设备 ID 无效")
    if device_id is not None and plan.device_id not in (None, device_id):
        raise QueryPlanError("查询计划的节点与请求节点不一致，请明确设备范围", clarification=True)
    scope = device_id or plan.device_id
    plan.device_id = scope
    plan.limit = min(plan.limit, max_rows)
    metric = plan.metric
    inventory = metric in _INVENTORY
    numeric = metric in _NUMERIC
    source = _SOURCE[metric]
    if len(plan.aggregations) != len(set(plan.aggregations)) or len(plan.group_by) != len(
        set(plan.group_by)
    ):
        raise QueryPlanError("聚合或分组不可重复")
    if inventory != (plan.window.kind == "current"):
        raise QueryPlanError(
            "设备清单/在线数量只支持 current；历史指标必须指定历史窗口", clarification=True
        )
    if plan.mode == "details":
        if metric in _DISTINCT_DEVICES:
            raise QueryPlanError("去重设备数量指标仅支持 aggregate；记录明细使用对应的记录指标")
        if plan.aggregations or plan.group_by or plan.bucket != "none":
            raise QueryPlanError("明细查询不可同时聚合、分组或分桶")
    elif not plan.aggregations or (not numeric and plan.aggregations != ["count"]):
        raise QueryPlanError("数值指标支持 avg/min/max/count，记录或设备数量只支持 count")
    allowed_groups: set[Dimension] = {"device_id", "device_type", "firmware_version"}
    if source == "iot_logs":
        allowed_groups.update({"module", "level"})
    elif source == "iot_diagnoses":
        allowed_groups.update({"fault_type", "error"})
    if set(plan.group_by) - allowed_groups:
        raise QueryPlanError("分组维度不适用于所选指标")
    if inventory and plan.bucket != "none":
        raise QueryPlanError("当前设备状态不支持历史时间分桶", clarification=True)
    f = plan.filters
    if (
        f.level is not None or f.module is not None or f.message_contains is not None
    ) and source != "iot_logs":
        raise QueryPlanError("日志过滤仅适用于日志指标")
    if (f.fault_type is not None or f.diagnosis_status != "all") and source != "iot_diagnoses":
        raise QueryPlanError("诊断过滤仅适用于诊断指标")
    if (f.value_min is not None or f.value_max is not None) and not numeric:
        raise QueryPlanError("数值阈值仅适用于数值遥测指标")
    if f.value_min is not None and f.value_max is not None and f.value_min > f.value_max:
        raise QueryPlanError("数值下限不得超过上限")
    window = _window(plan.window, now, utc_offset_minutes)
    parameters: dict[str, Any] = {"row_limit": plan.limit + 1}
    where: list[str] = []
    if inventory:
        from_sql = "iot_devices d LEFT JOIN iot_state s ON s.device_id = d.device_id"
        if metric != "devices":
            where.append(f"COALESCE(s.online, 0) = {1 if metric == 'online_devices' else 0}")
        device_expr = "d.device_id"
    else:
        # The only allowed join is many-to-one metadata enrichment. Joining two
        # event streams would multiply rows and corrupt aggregates.
        from_sql = f"{source} t JOIN iot_devices d ON d.device_id = t.device_id"
        device_expr = "t.device_id"
        time_expr = f"t.{_TIME[source]}"
        where.append("julianday(" + time_expr + ") < julianday(:query_end)")
        parameters["query_end"] = window["end_utc"] or now.isoformat()
        if window["start_utc"] is not None:
            where.append(f"julianday({time_expr}) >= julianday(:query_start)")
            parameters["query_start"] = window["start_utc"]
    if scope is not None:
        where.append(f"{device_expr} = :device_id")
        parameters["device_id"] = scope
    for field in ("device_type", "firmware_version"):
        value = getattr(f, field)
        if value is not None:
            where.append(f"d.{field} = :{field}")
            parameters[field] = value
    for field in ("level", "module", "fault_type"):
        value = getattr(f, field)
        if value is not None:
            where.append(f"t.{field} = :{field}")
            parameters[field] = value
    if f.message_contains is not None:
        where.append("instr(lower(t.message), lower(:message_contains)) > 0")
        parameters["message_contains"] = f.message_contains
    if f.diagnosis_status != "all":
        where.append("t.error IS " + ("NULL" if f.diagnosis_status == "succeeded" else "NOT NULL"))
    for field, op in (("value_min", ">="), ("value_max", "<=")):
        value = getattr(f, field)
        if value is not None:
            where.append(f"t.{metric} {op} :{field}")
            parameters[field] = value
    dimensions = {
        "device_id": device_expr,
        "device_type": "d.device_type",
        "firmware_version": "d.firmware_version",
    }
    if source == "iot_logs":
        dimensions.update({"module": "t.module", "level": "t.level"})
    elif source == "iot_diagnoses":
        dimensions.update({"fault_type": "t.fault_type", "error": "t.error"})
    groups: list[str] = []
    selections: list[str] = []
    aliases: set[str] = set()
    if plan.mode == "aggregate":
        if plan.bucket != "none":
            fmt = "%Y-%m-%d %H:00:00" if plan.bucket == "hour" else "%Y-%m-%d"
            parameters["bucket_format"] = fmt
            parameters["bucket_offset"] = f"{utc_offset_minutes:+d} minutes"
            selections.append(f"strftime(:bucket_format, {time_expr}, :bucket_offset) AS bucket")
            groups.append("bucket")
        for dim in plan.group_by:
            selections.append(f"{dimensions[dim]} AS {dim}")
            groups.append(dim)
        for agg in plan.aggregations:
            value = f"t.{metric}" if numeric else "*"
            if metric in _DISTINCT_DEVICES:
                value = "DISTINCT t.device_id"
            selections.append(f"{agg.upper()}({value}) AS {agg}")
        if numeric:
            selections.append(f"COUNT(t.{metric}) AS sample_count")
        aliases = set(groups) | set(plan.aggregations)
    elif inventory:
        selections = [
            "d.device_id",
            "d.name",
            "d.device_type",
            "d.firmware_version",
            "COALESCE(s.online, 0) AS online",
            "s.received_at",
            "s.rssi",
            "s.temperature",
        ]
        aliases = {"device_id"}
    else:
        details = {
            "iot_telemetry": "t.id, t.device_id, t.temperature, t.rssi, t.uptime, t.wifi_status, t.mqtt_status, t.received_at",
            "iot_logs": "t.id, t.device_id, t.level, t.module, t.message, t.timestamp",
            "iot_diagnoses": "t.diagnosis_id, t.device_id, t.fault_type, t.fault_name, t.cause, t.confidence, t.error, t.created_at",
        }
        selections = [details[source]]
        aliases = {"device_id", "time"}
    sql = f"SELECT {', '.join(selections)} FROM {from_sql}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if groups:
        sql += " GROUP BY " + ", ".join(str(index + 1) for index in range(len(groups)))
    orders = []
    if plan.sort:
        key = "bucket" if plan.sort.key == "time" and plan.mode == "aggregate" else plan.sort.key
        if key not in aliases:
            raise QueryPlanError("排序字段必须是结果中的聚合、分组或明细时间")
        expression = f"julianday({time_expr})" if key == "time" else key
        orders.append(f"{expression} {plan.sort.direction.upper()}")
    orders.extend(f"{dim} ASC" for dim in groups)
    if plan.mode == "details":
        if inventory:
            orders.append("d.device_id ASC")
        else:
            if not plan.sort or plan.sort.key != "time":
                orders.append(f"julianday({time_expr}) DESC")
            orders.append("t.diagnosis_id ASC" if source == "iot_diagnoses" else "t.id ASC")
    if orders:
        sql += " ORDER BY " + ", ".join(orders)
    sql += " LIMIT :row_limit"
    return CompiledQuery(
        sql, parameters, scope, plan.limit, plan.model_dump(), METRIC_CATALOG[metric], window
    )
