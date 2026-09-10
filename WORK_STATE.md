# IoT Diagnosis 项目工作状态

更新时间：2026-09-10（Asia/Shanghai）

## 当前目标

在本地完成前后端与新版 `IoT Diagnosis MCP Server v1.0` 的联调，用新版统一 MCP 替换旧 MCP，并接入 MySQL 与 Qdrant 进行持久化测试。

## 已完成

- 新版统一 MCP 位于 `mcp-services/iot_diagnosis/`，包含 6 个诊断工具。
- 已移除旧 RAG / IoT MCP 相关代码、旧维修审批与执行接口及对应前端 UI。
- 新规范文件保留在 `specs/iot-diagnosis-mcp-spec-v1.0.md`。
- 已实现 MQTT `fault`、`heartbeat` 消息和设备离线检测。
- 已实现可配置的 LLM Router / Diagnosis 调用；未配置模型密钥时使用 `heuristic_fallback`。
- 已实现人工确认故障案例的后端接口与前端弹窗。
- 已实现 MySQL 镜像写入和 Qdrant 向量索引：
  - 新文件：`mcp-services/iot_diagnosis/external.py`
  - MySQL 表：`device`、`device_status`、`device_log`、`knowledge_document`、`fault_case`、`diagnosis_record`
  - Qdrant 使用 384 维确定性特征向量，集合名由环境变量配置。
  - SQLite 仍为主存储；MySQL / Qdrant 当前采用双写与失败回退模式。
- `docker-compose.yml` 已加入：
  - `mysql:8.4.11`，本机端口 `3306`
  - `qdrant/qdrant:v1.19.1`，本机端口 `6333`
  - MCP 的 MySQL / Qdrant 环境变量和健康依赖
- `mcp-services/pyproject.toml` 已加入 `PyMySQL==1.2.0`。
- `.env.example` 已加入 MySQL / Qdrant 配置示例。
- 新 MCP 与模拟器镜像已重新构建成功。
- 已修复启用 Qdrant 后、无实时状态参数的知识检索会返回 `RETRIEVAL_FAILED` 的候选项缩进错误。
- Qdrant 集合初始化已改为先查询、仅在 404 时创建，容器重启不会再因集合已存在的 409 响应而降级。
- SQLite 启动快照改为批量同步 MySQL，数千条状态与日志不再逐条创建连接阻塞服务启动。
- README 已补充 MySQL / Qdrant 端口、持久化卷、环境变量和健康状态说明。

## 已通过的验证

- 后端测试：10 passed。
- MCP 测试：9 passed（包含 Qdrant 已有集合和无实时状态向量检索回归测试）。
- 前端 lint 与 production build：通过。
- MCP 在线冒烟：6 个工具、知识检索、诊断和人工确认门禁通过。
- 本地全栈冒烟：前端 200、同源代理、认证、会话 CRUD 和 SSE 通过。
- 经后端真实写入人工确认案例 `FC19D3B41`，返回 `mysql_saved: true`、`vector_indexed: true`。
- MySQL 已查到 `FC19D3B41`；Qdrant 集合状态为 `ok`，已查到对应向量点。
- 前端 lint 修复已验证并提交，仓库工作树干净。

## 当前本地运行状态

执行 `docker compose ps` 时以下服务均为 Up：

- frontend：本地开发服务，`http://localhost:3000`
- backend：`127.0.0.1:8000`，healthy
- mqtt：`127.0.0.1:1883`
- mysql：`127.0.0.1:3306`，healthy
- qdrant：`127.0.0.1:6333`，healthy
- iot-diagnosis-mcp：`127.0.0.1:9001`，健康接口三种存储均为 connected
- iot-simulator：running

## 当前待处理问题

- 当前本地联调目标已完成，没有已知阻塞问题。

## 下一步

1. 如需真实模型诊断，配置 `DIAGNOSIS_LLM_API_KEY` 和 `DIAGNOSIS_LLM_MODEL` 后补跑 LLM Router / Diagnosis 在线验收。

## 重要文件

- `compose.yaml`
- `mcp-services/.env.example`
- `mcp-services/pyproject.toml`
- `mcp-services/iot_diagnosis/external.py`
- `mcp-services/iot_diagnosis/repository.py`
- `mcp-services/iot_diagnosis/retrieval.py`
- `mcp-services/iot_diagnosis/server.py`
- `specs/iot-diagnosis-mcp-spec-v1.0.md`

## Git 状态

- 项目根目录已建立主 Git 仓库，默认分支为 `main`，跟踪 frontend、backend、deploy、specs、Compose 配置和项目文档。
- frontend 原有提交历史已完整导入主仓库，不再保留嵌套 `.git`。
- `mcp-services/` 是唯一的独立子目录仓库，默认分支为 `main`；首个提交为 `ac596d3 Initial IoT diagnosis MCP server`。
- MCP 仓库通过 `.gitignore` 排除了 SQLite 运行数据、本地 `.env`、Python/pytest 缓存和构建产物。
- 主仓库通过根 `.gitignore` 排除 `mcp-services/`、运行数据、虚拟环境、依赖目录和构建产物。
- 最近相关提交：
  - `d7c73a0 Fix frontend lint compatibility`
  - `ad9542a Add verified fault case workflow`
  - `1513ddb Remove legacy repair approval UI`
  - `ff34a6a Proxy backend through same-origin site route`
- frontend 原仓库 bundle 与 `.git` 元数据备份位于 `D:\last-work-repo-backups\`。
