# 小yi 后端

FastAPI 主服务，负责用户会话、对话、Agent 运行、SSE 事件、MCP 接入策略和审计。设备与知识业务由统一 IoT Diagnosis MCP 提供。

API 入口只负责组合路由；认证、对话、消息提交/分页、运行查询/重试/SSE 分别位于
`app/api/auth.py`、`conversations.py`、`messages.py` 和 `runs.py`。运行恢复、上下文预算与
事件批量持久化位于独立 service，API handler 不承担后台执行状态机。

## 本地运行

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

复制 `.env.example` 为 `.env` 后配置 `OPENAI_API_KEY`。未配置时使用确定性的演示 Runtime，方便前后端联调；生产环境应设置 `AGENT_RUNTIME=openai`，缺少密钥时服务会拒绝启动 Agent 运行。

开发账号：`admin / admin123`、`operator / operator123`。它们只用于本地演示，生产环境必须关闭自动播种并更换凭据。

## 容器部署

镜像使用根目录 `compose.yaml` 或本目录 `Dockerfile` 构建。线上配置以
`.env.production.example` 为模板，并至少设置随机 `APP_SECRET_KEY`、持久化
`DATABASE_URL`、`SEED_DEMO_USERS=false`，以及真实模型配置。

前端默认通过同源代理访问后端，因此推荐保持 `SESSION_COOKIE_SAMESITE=lax` 和
`SESSION_COOKIE_SECURE=true`。如果浏览器必须跨站直连后端，则改为
`SESSION_COOKIE_SAMESITE=none`；服务会拒绝不安全的 `none + secure=false` 组合。

## 对话上下文预算与消息分页

长对话不再整体进入模型输入或一次性下发前端：

- Agent 运行按预算从新到旧选择完整 user/assistant 轮次，先省略旧附件正文再省略最旧轮次；
  当前消息始终保留，自身超预算时运行以 `CONTEXT_INPUT_TOO_LARGE` 失败。
  预算元数据（纳入/省略消息数、附件字符、估算 token）记录在 run 的 `runtime_state.context`。
- 配置：`AGENT_CONTEXT_MAX_INPUT_TOKENS`（默认 60000）、
  `AGENT_CONTEXT_MAX_HISTORY_MESSAGES`（100）、`AGENT_ATTACHMENT_MAX_CHARS`（50000）、
  `AGENT_ATTACHMENTS_TOTAL_MAX_CHARS`（100000）。
- `GET /conversations/{id}/messages` 支持游标分页：`limit` 默认 50、最大 200，
  `before` 读取更早消息，响应含 `items`、`next_cursor`、`has_more`；不传参数时返回最近一页。
  旧客户端可临时设置 `MESSAGE_PAGINATION_LEGACY_DEFAULT=true` 恢复全量返回一个版本。

## 数据保留与运行事件治理

- 运行事件经 `RunEventBuffer` 合并 `answer.delta`（默认 256 字符或 200ms）后批量提交，
  工具输出超过 64 KiB 时持久化摘要、原始字节数与 SHA-256。
- 保留策略覆盖未绑定附件（24h）、过期 Session（过期后 7 天宽限）与可重建的
  `answer.delta`（完成后 24h 压缩；失败 run 保留 7 天诊断期）。已绑定附件、对话、
  消息与审计记录不受影响。
- 默认 dry-run：`python -m app.cli retention` 输出各类候选统计；确认后设置
  `RETENTION_DELETE_ENABLED=true` 并执行 `python -m app.cli retention --execute`
  （或由后台周期任务按 `RETENTION_INTERVAL_HOURS` 自动清理）。
- 前端移除草稿附件时调用 `DELETE /attachments/{id}`；仅未绑定附件可删。

## 健康检查、日志与指标

- `GET /live`：进程存活探针，恒 200；`GET /health` 保持兼容（等价 /live）。
- `GET /ready`：业务就绪探针，检查数据库 `SELECT 1`、schema 迁移版本与 Dispatcher 状态，
  返回 `ready|degraded|not_ready` 与逐组件 `checks`；必需组件失败返回 503。
  容器 HEALTHCHECK 已切换到 `/ready`。
- 必需 MCP 依赖通过 `MCP_REQUIRED_SERVER_KEYS` 声明（如 `iot-diagnosis-local`）；
  必需 MCP 离线 → 503，未声明的 MCP 不参与就绪判定。
- `GET /metrics`：Prometheus 指标（HTTP 请求量/延迟、Agent run 状态与耗时、SSE 连接数、
  MCP 调用结果与延迟、上下文预算省略量、保留策略清理量）。
- 日志为 JSON 结构化输出，公共字段含 `timestamp/level/service/event`，以及存在时的
  `request_id/run_id/trace_id/device_id/duration_ms/error_code`；Agent 失败保留内部堆栈于日志，
  对客户端只返回稳定公共错误结构。
- 错误分类：`CONFIGURATION_ERROR`、`VALIDATION_ERROR`、`DEPENDENCY_UNAVAILABLE`（可重试）、
  `RUN_INTERRUPTED`（可由用户重试）、`DATABASE_SCHEMA_BEHIND/AHEAD`、`MODEL_CACHE_INCOMPLETE`。
