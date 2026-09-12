# 小yi 通用智能体

一个 ChatGPT 风格的通用 Agent，使用 FastAPI、OpenAI Agents SDK 和动态 MCP 服务。浏览器只访问主后端；设备状态、日志、知识检索、故障案例与诊断由统一的 IoT Diagnosis MCP Server 提供，设备修复命令的下发、审批与恢复验证由独立的 IoT Control MCP Server 提供，Agent 可自主完成"诊断 → 决策 → 执行 → 验证"的闭环运维（低风险动作直接执行，高风险动作需在界面一键批准）。

## 项目结构

- `frontend/`：小yi 对话界面
- `backend/`：认证、对话、Agent 运行、MCP 管理和审计边界
- `mcp-services/`：统一 IoT Diagnosis MCP、IoT Control MCP、MQTT 接入与模拟器
- `specs/`：IoT Diagnosis MCP v1.0 基线、v1.1 completion、v1.2 core-model、v1.3 discovery 与 IoT Control MCP v1.0 规格

## 仓库边界

本地目录由两个 Git 仓库组成：

- 主仓库位于项目根目录，跟踪 `frontend/`、`backend/`、`deploy/`、`specs/`、Compose 配置和项目文档。
- `mcp-services/` 是独立仓库，并由主仓库的 `.gitignore` 排除。

分别克隆时，请将 MCP 仓库放在主仓库的 `mcp-services/` 目录，确保 `compose.yaml` 中的构建路径无需修改。

## 本地端口

- 前端：`http://localhost:3000`
- FastAPI：`http://127.0.0.1:8000`
- IoT Diagnosis MCP：`http://127.0.0.1:9001/mcp`
- IoT Control MCP：`http://127.0.0.1:9002/mcp`
- MySQL：`127.0.0.1:3306`
- Qdrant：`http://127.0.0.1:6333`
- Retrieval Models：`http://127.0.0.1:9010/health`

## 本地全套启动

Docker Desktop 启动后，一次拉起主后端、IoT Diagnosis MCP、MQTT、MySQL、Qdrant 和模拟设备：

```powershell
docker compose up -d --build
```

前端保留热更新模式：

```powershell
cd frontend
npm run dev
```

首次启动或重建数据卷后，注册并启用本地 MCP 工具：

```powershell
cd backend
python scripts/bootstrap_local_mcp.py
```

运行状态可用 `docker compose ps` 查看；停止时运行 `docker compose down`。数据保存在
Docker 命名卷中，普通停止不会清空对话、知识库或设备数据。

开发环境没有 `OPENAI_API_KEY` 时，主 Agent 使用确定性 Mock Runtime；配置密钥并设置 `AGENT_RUNTIME=openai` 后启用 OpenAI Agents SDK。诊断 MCP 可另外通过 `DIAGNOSIS_LLM_API_KEY`、`DIAGNOSIS_LLM_MODEL` 和 `DIAGNOSIS_LLM_BASE_URL` 接入兼容 Chat Completions 的模型；未配置时会明确使用启发式回退。

诊断服务以 SQLite 为本地事实源，同时镜像写入 MySQL，并将知识文档和已由人工确认的故障案例写入 Qdrant。外部写入失败时会进入 SQLite outbox 并由后台任务重试；写入结果会明确返回 `complete` 或 `pending`。Compose 默认使用 GPU 上的 `Qwen3-Embedding-0.6B` 生成 1024 维语义向量，并由 `Qwen3-Reranker-0.6B` 按官方 yes/no CausalLM 方式重排；本地 hash 与加权排序保留为降级方案。Embedding 与 Qdrant 写入支持批处理，`rebuild_vector_index` 可从 SQLite 重建全部或指定来源的向量。实时状态问题由 Rule Router 直接返回 `answer` 和 `realtime_state`，不调用诊断模型；复杂问题进入多源 RAG 与诊断流程。诊断结果附带证据来源，并可使用 `get_diagnosis_trace` 查询完整结果快照、最终上下文和观测字段。`list_devices`、`list_diagnoses` 和 `list_knowledge_documents` 提供设备、诊断历史和知识目录的过滤与分页发现能力。

## 自主运维闭环

IoT Control MCP（端口 9002）让 Agent 从"只诊不治"升级为闭环处置：低风险动作（重连 MQTT/WiFi、传感器校准、调整上报间隔）由 Agent 直接下发并轮询验证；高风险动作（重启设备、固件升级）由 Agent 创建修复提案，在聊天界面的审批卡上一键批准后由系统执行并自动验证恢复。命令走 `iot/{device_id}/cmd` 下行主题，设备回执 `cmd_ack`，Control MCP 在验证窗口内采样状态与日志判定是否恢复。恢复成功后 Control MCP 发布修复完成事件（`iot/{device_id}/remediation`），诊断服务消费事件并自动沉淀为已验证故障案例（`verified_by=auto-remediation:{command_id}`），案例库随自主运维持续积累——两个 MCP 之间只通过 MQTT 主题契约通信。详见 `specs/iot-control-mcp-spec-v1.0.md`。

## 诊断存储配置

Docker Compose 默认创建 `iot_diagnosis` MySQL 数据库和 `iot_diagnosis_qwen3` Qdrant 集合，数据分别保存在 `mysql-data`、`qdrant-data` 和 `diagnosis-data` 命名卷。可在启动前通过环境变量覆盖本地数据库密码：

```powershell
$env:MYSQL_PASSWORD = "change-this-password"
$env:MYSQL_ROOT_PASSWORD = "change-this-root-password"
docker compose up -d --build
```

直接运行 MCP 时，可复制 `mcp-services/.env.example` 中的配置，并按需要设置：

```text
DIAGNOSIS_MYSQL_DSN=mysql://iot_diagnosis:password@127.0.0.1:3306/iot_diagnosis
DIAGNOSIS_QDRANT_URL=http://127.0.0.1:6333
DIAGNOSIS_QDRANT_COLLECTION=iot_diagnosis_qwen3
DIAGNOSIS_SYNC_RETRY_SECONDS=30
DIAGNOSIS_EMBEDDING_PROVIDER=openai_compatible
DIAGNOSIS_EMBEDDING_BASE_URL=http://127.0.0.1:9010/v1
DIAGNOSIS_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
DIAGNOSIS_EMBEDDING_DIMENSIONS=1024
DIAGNOSIS_VECTOR_BATCH_SIZE=32
DIAGNOSIS_RETRIEVAL_MODEL_HEALTH_URL=http://127.0.0.1:9010/health
DIAGNOSIS_RERANKER_PROVIDER=qwen3
DIAGNOSIS_RERANKER_URL=http://127.0.0.1:9010/rerank
```

启动后访问 `http://127.0.0.1:9001/health` 检查进程存活，访问 `http://127.0.0.1:9001/ready` 检查依赖是否就绪。正常情况下 `storage.sqlite`、`storage.mysql` 和 `storage.qdrant` 均为 `connected`，`storage.outbox.pending` 为零，且 `retrieval_models.status` 为 `ready`；已配置依赖不可用时 readiness 返回 HTTP 503。

生产环境可设置 `DIAGNOSIS_MCP_BEARER_TOKEN` 保护 `/mcp`。随后用同一个值重新注册后端连接：

```powershell
cd backend
python scripts/bootstrap_local_mcp.py --credential "replace-with-a-long-random-token"
```

## 知识摄取与评测

在 `mcp-services` 目录中摄取 TXT、Markdown 或 PDF：

```powershell
..\backend\.venv\Scripts\python.exe -m scripts.ingest_documents .\docs\mqtt-guide.pdf --source mqtt_docs --document-id mqtt-guide --title "MQTT Guide"
```

相同 `document-id` 再次摄取会原子替换旧分块。运行确定性 RAG/Router 评测：

```powershell
..\backend\.venv\Scripts\python.exe -m scripts.evaluate_rag --database .\data\iot_diagnosis_eval.db
```

运行 Compose 中真实 Qwen3 Embedding/Reranker 评测：

```powershell
docker exec last-work-iot-diagnosis-mcp-1 python /app/scripts/evaluate_rag.py --profile live-retrieval --database /app/data/iot_diagnosis.db
```

## MQTT 联调

Docker Desktop 启动后，可运行本地开发 Broker：

```powershell
docker compose up -d mqtt
```

然后运行符合新 Topic 规范的模拟节点：

```powershell
python -m iot_diagnosis.simulator --device-id ESP32_05 --scenario mqtt_timeout
```

新服务订阅 `iot/{device_id}/status`、`iot/{device_id}/telemetry`、
`iot/{device_id}/logs`、`iot/{device_id}/fault` 和 `iot/{device_id}/heartbeat`，并根据心跳超时判定离线。诊断 MCP 不提供设备重启、固件更新或网络配置修改等控制能力。

开发 Broker 仅绑定 `127.0.0.1` 且允许匿名连接，只用于本机联调；实验室或生产环境应启用用户名、TLS 和 Topic ACL。

## 验证

```powershell
backend\.venv\Scripts\python.exe -m pytest -q backend\tests
Push-Location mcp-services
..\backend\.venv\Scripts\python.exe -m pytest -q
Pop-Location
cd frontend
npm run build
```

## 前后端联调

分别启动后端和前端：

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

cd frontend
npm run dev
```

浏览器使用 `http://localhost:3000`。前端默认请求
`/api/backend/api/v1`，由前端同源代理转发到 `BACKEND_BASE_URL`（默认可在
`frontend/.env.local` 中设为 `http://localhost:8000`）。这样本地和线上共用同一套
Cookie、CSRF 与 SSE 链路，不依赖第三方 Cookie。

两个服务启动后，可运行包含登录、会话增删改查、消息提交和 SSE 的真实链路检查：

```powershell
cd backend
python scripts/smoke_frontend_backend.py
```

直接访问后端并验证 CORS 时，可额外传入：

```powershell
python scripts/smoke_frontend_backend.py --api-base http://localhost:8000/api/v1
```

后端已提供容器镜像；本地可在 Docker Desktop 启动后运行 `docker compose up --build backend`。
