"""Prometheus 指标（specs WP-12 / §11.3、§16.5）。

第一版覆盖：HTTP 请求量/错误量/延迟、Agent run 状态与耗时、SSE 连接、
MCP 调用结果与延迟、上下文预算省略量、保留策略清理量。
不在请求路径扫描大表；数据库规模指标由后续周期采样器补充。
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "xiaoyi_http_requests_total",
    "HTTP 请求量（按方法/路由/状态码）",
    ["method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "xiaoyi_http_request_duration_seconds",
    "HTTP 请求延迟",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)

AGENT_RUNS = Counter(
    "xiaoyi_agent_runs_total",
    "Agent run 终态数量（completed/failed/interrupted）",
    ["status"],
)
AGENT_RUN_DURATION = Histogram(
    "xiaoyi_agent_run_duration_seconds",
    "Agent 运行时长（认领到终态）",
    buckets=(0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600),
)

SSE_CONNECTIONS = Gauge(
    "xiaoyi_sse_connections_active",
    "当前 SSE 事件流连接数",
)

MCP_CALLS = Counter(
    "xiaoyi_mcp_calls_total",
    "MCP 工具调用数量（按服务与结果）",
    ["server", "result"],
)
MCP_LATENCY = Histogram(
    "xiaoyi_mcp_call_duration_seconds",
    "MCP 工具调用延迟",
    ["server"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20),
)

CONTEXT_ESTIMATED_TOKENS = Histogram(
    "xiaoyi_context_estimated_input_tokens",
    "上下文估算输入 token 分布",
    buckets=(500, 1000, 2000, 4000, 8000, 16000, 32000, 64000, 128000),
)
CONTEXT_OMITTED_MESSAGES = Counter(
    "xiaoyi_context_omitted_messages_total",
    "因预算被省略的历史消息数量",
)

RETENTION_DELETED = Counter(
    "xiaoyi_retention_deleted_total",
    "保留策略删除数量（按类别）",
    ["kind"],
)
