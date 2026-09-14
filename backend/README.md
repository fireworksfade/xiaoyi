# 小yi 后端

FastAPI 主服务，负责用户会话、对话、Agent 运行、SSE 事件、MCP 接入策略和审计。设备与知识业务由统一 IoT Diagnosis MCP 提供。

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
