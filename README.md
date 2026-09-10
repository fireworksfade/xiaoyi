# 小yi 通用智能体

一个 ChatGPT 风格的通用 Agent，使用 FastAPI、OpenAI Agents SDK 和动态 MCP 服务。浏览器只访问主后端；设备状态、日志、知识检索、故障案例与诊断由统一的 IoT Diagnosis MCP Server 提供。

## 项目结构

- `frontend/`：小yi 对话界面
- `backend/`：认证、对话、Agent 运行、MCP 管理和审计边界
- `mcp-services/`：统一 IoT Diagnosis MCP、MQTT 接入与模拟器
- `specs/`：IoT Diagnosis MCP v1.0 规格

## 仓库边界

本地目录由两个 Git 仓库组成：

- 主仓库位于项目根目录，跟踪 `frontend/`、`backend/`、`deploy/`、`specs/`、Compose 配置和项目文档。
- `mcp-services/` 是独立仓库，并由主仓库的 `.gitignore` 排除。

分别克隆时，请将 MCP 仓库放在主仓库的 `mcp-services/` 目录，确保 `compose.yaml` 中的构建路径无需修改。

## 本地端口

- 前端：`http://localhost:3000`
- FastAPI：`http://127.0.0.1:8000`
- IoT Diagnosis MCP：`http://127.0.0.1:9001/mcp`
- MySQL：`127.0.0.1:3306`
- Qdrant：`http://127.0.0.1:6333`

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

诊断服务以 SQLite 为主存储，同时镜像写入 MySQL，并将知识文档和已由人工确认的故障案例写入 Qdrant。外部存储暂时不可用时服务会继续使用 SQLite 和本地检索，并在健康检查中标记降级状态。检索采用关键词、确定性 384 维特征向量与统一重排，诊断结果附带证据来源和观测字段。

## 诊断存储配置

Docker Compose 默认创建 `iot_diagnosis` MySQL 数据库和 `iot_diagnosis_knowledge` Qdrant 集合，数据分别保存在 `mysql-data`、`qdrant-data` 和 `diagnosis-data` 命名卷。可在启动前通过环境变量覆盖本地数据库密码：

```powershell
$env:MYSQL_PASSWORD = "change-this-password"
$env:MYSQL_ROOT_PASSWORD = "change-this-root-password"
docker compose up -d --build
```

直接运行 MCP 时，可复制 `mcp-services/.env.example` 中的配置，并按需要设置：

```text
DIAGNOSIS_MYSQL_DSN=mysql://iot_diagnosis:password@127.0.0.1:3306/iot_diagnosis
DIAGNOSIS_QDRANT_URL=http://127.0.0.1:6333
DIAGNOSIS_QDRANT_COLLECTION=iot_diagnosis_knowledge
```

启动后访问 `http://127.0.0.1:9001/health`。正常情况下 `storage.sqlite`、`storage.mysql` 和 `storage.qdrant` 均为 `connected`；未配置的外部存储显示 `disabled`，连接失败则显示 `fallback` 并在 `errors` 中给出错误类型。

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
`iot/{device_id}/logs`、`iot/{device_id}/fault` 和 `iot/{device_id}/heartbeat`，并根据心跳超时判定离线。v1.0 只提供诊断与人工验证后的案例入库，
不提供设备重启、固件更新或网络配置修改等控制能力。

开发 Broker 仅绑定 `127.0.0.1` 且允许匿名连接，只用于本机联调；实验室或生产环境应启用用户名、TLS 和 Topic ACL。

## 验证

```powershell
backend\.venv\Scripts\python.exe -m pytest -q backend\tests
backend\.venv\Scripts\python.exe -m pytest -q mcp-services\tests
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
