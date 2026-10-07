# Xiaoyi IoT 平台

基于智能体和 MCP 的 IoT 设备诊断与控制平台。前端提供对话、知识文档和记忆管理界面；FastAPI 后端负责认证、对话、Agent 运行、工具策略与记忆管理；统一 IoT MCP 服务提供设备诊断、知识检索、Text2SQL 历史数据查询和设备控制能力。

## 当前架构

| 组件 | 目录或服务 | 职责 |
| --- | --- | --- |
| 前端 | `packages/frontend` | React 19 + Vinext，浏览器通过同源 `/api/backend` 代理访问后端 |
| 后端 | `packages/backend` | FastAPI、SQLite、Agent 运行、SSE、MCP 工具目录与审批策略 |
| IoT MCP | `packages/mcp-services/iot_mcp` | 单个 Streamable HTTP 服务，整合诊断与控制工具 |
| 共享检索库 | `packages/retrieval` | 两个 Python 服务共用的 embedding 与 Qdrant 请求、响应校验；不负责业务数据和权限 |
| 基础设施 | `compose.yaml` | MQTT、Qdrant、设备模拟机群及后端和 MCP 容器 |

未配置外部检索 API 时，默认 Compose 使用本地 hash embedding 和 weighted reranker（Portable 档位），无需 GPU 或模型下载。可在根目录 `.env` 配置 API 作为主 Embedding / Reranker，再叠加本地 Qwen 0.6B 兜底；也可选择本地 Qwen 主档位，见下文「检索模型档位」。后端默认使用演示 Runtime；若数据库中已保存模型配置，运行时会使用该配置。默认不启动 Qwen3 模型服务，是为了让开发环境无需 GPU、模型下载或较长的冷启动等待即可运行。

运行状态由 Agent Run、运行事件和 SSE 事件流统一管理。平台不再维护独立的 IoT operation workflow 状态机、完成门或工作流详情接口；已有数据库升级到最新迁移时会自动删除旧的 workflow 数据表。

前端业务组件统一放在 `features/`，`components/ui/` 保留基础 UI。平台聊天通过 `ToolExecutor` 完成诊断关联、记忆边界、结果处理与失败后再诊断。目录与维护入口见 [项目结构](docs/project-structure.md)，结构与配置说明见 [架构简化说明](docs/architecture-simplification.md)。

## 快速开始

需要 Docker Compose 和 Node.js 22.13 或更高版本。基础 Compose **不启动前端**，因此按下面两步分别启动。

### 1. 启动后端与 IoT MCP

在仓库根目录运行：

```bash
docker compose up -d --build
docker compose ps
docker compose exec -T backend python scripts/bootstrap_local_mcp.py
```

最后一条命令向后端注册 `http://iot-mcp:9000/mcp`，测试连接、刷新工具目录并配置风险策略。重复运行可刷新已有连接。开发环境使用演示账号 `admin / admin123`；该账号只适用于本地开发。

首次启动或重建数据卷后，导入随项目提供的真实技术资料：

```bash
docker compose exec -T iot-mcp python -m scripts.ingest_recommended_documents
```

该命令将 20 份官方文档快照和 12 份整理的诊断指南写入持久化知识库，同时建立全文与 Qdrant 向量索引，覆盖 MQTT、WiFi、传感器和 ESP32 设备。官方快照正文保留来源链接；这些资料属于技术文档，不是现场故障案例。重复执行会按固定文档 ID 替换对应资料，不会重复添加。输出中的 `vector_indexed: true` 和 `sync_status: complete` 表示向量同步完成；`pending` 表示等待后台重试。导入后可在前端“知识库”查看，并通过 `search_knowledge` 检索。

### 2. 启动前端

另开一个终端，在仓库根目录执行（Node.js >= 22.13，npm >= 10）：

```bash
npm ci
npm run dev
```

打开 [前端](http://127.0.0.1:3000)。开发脚本默认监听 `127.0.0.1`；本地前端默认把 `/api/backend` 请求代理到 `http://127.0.0.1:8000`。需要更改后端地址时，在 `packages/frontend/.env.local` 中设置 `BACKEND_BASE_URL`。

项目统一使用 npm workspaces，依赖锁文件为根目录的 `package-lock.json`。安装与 CI 均在根目录运行 `npm ci`；为前端添加依赖使用 `npm install <包名> --workspace=packages/frontend`（开发依赖加 `-D`）。前端目录内也可运行 `npm run dev`。

### 前端运行与容器化

当前推荐的本地开发方式是：Docker Compose 管理后端与基础设施，前端在宿主机通过 `npm run dev` 运行。前端尚未提供 Dockerfile 或 Compose 服务；`docker compose up`、`restart` 和 `down` 均不管理前端进程。

长期运行或交付时，可增加前端容器，将整套服务的启动、依赖版本和自动重启统一到 Compose。开发时仍可保留本机运行。容器内前端需要监听 `0.0.0.0`，服务端代理的 `BACKEND_BASE_URL` 应使用 `http://backend:8000`；浏览器继续访问同源 `/api/backend`。

前端包含 Vinext 服务端渲染与 API 代理，依赖 Cloudflare Workers 运行时。仅托管静态构建文件不足以运行完整应用。`npm run build` 用于构建，当前 `npm start` 调用 `wrangler dev`，属于本地预览；正式部署需明确运行时与后端连接配置。以上容器化方案尚未实现，不能直接作为现有启动步骤使用。

### 服务地址与检查

| 地址 | 用途 |
| --- | --- |
| [127.0.0.1:3000](http://127.0.0.1:3000) | 前端（单独启动） |
| [127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) | 后端 API 文档 |
| [127.0.0.1:8000/ready](http://127.0.0.1:8000/ready) | 后端业务就绪检查 |
| [127.0.0.1:9000/ready](http://127.0.0.1:9000/ready) | IoT MCP 就绪检查 |
| [127.0.0.1:6333/dashboard](http://127.0.0.1:6333/dashboard) | Qdrant 管理界面 |
| [127.0.0.1:9010/ready](http://127.0.0.1:9010/ready) | 检索模型服务就绪检查（仅检索模型档位） |

MCP 服务连接成功后，前端“设置 → MCP 服务”中可查看服务及工具。注册脚本将查询与诊断工具设为只读策略、可发起的动作设为提案策略、需人工审批的写入与删除工具设为审批策略；未列入策略的工具保持禁用。

设备控制采用持久投递队列和按动作验收的恢复验证；缺少证据返回 `inconclusive`。命令投递状态、设备验收字段及工具 schema 升级步骤见 [IoT 工具可靠性说明](docs/iot-tool-reliability.md)。

## 配置

- Embedding / Reranker 的 API 配置统一放在仓库根目录 `.env`，模板见 [`.env.example`](.env.example)，字段与切换步骤见 [API 检索配置](docs/retrieval-api.md)。
- API 主模型 + 本地 Qwen 0.6B 兜底使用 `compose.retrieval-api-fallback.yaml`；两者均不可用时回退 hash / weighted，每次新请求继续优先 API。
- 后端本地运行配置参见 [`packages/backend/.env.example`](packages/backend/.env.example)。`AGENT_RUNTIME=mock` 可用于无模型密钥的联调；使用真实模型时配置模型 API 或相应环境变量。`FRONTEND_ORIGINS` 支持逗号分隔多来源，默认允许 `http://localhost:3000` 与 `http://127.0.0.1:3000`。
- IoT MCP 的 Compose 环境变量位于 [`compose.yaml`](compose.yaml)，本地运行示例见 [`packages/mcp-services/.env.example`](packages/mcp-services/.env.example)。诊断与控制共用 `IOT_MCP_HOST` / `IOT_MCP_PORT`（默认 9000）；配置 `DIAGNOSIS_MCP_BEARER_TOKEN` 后，所有 MCP 工具请求均须携带该令牌，`/ready` 保持可用于健康检查。默认 Portable 检索不依赖外部模型；Text2SQL 则需要有效的 `DIAGNOSIS_LLM_*` 模型配置。
- 当前 `compose.yaml` 使用开发密钥、演示账号和本地端口绑定。生产部署须另行配置密钥、账号、数据库和 Cookie 策略，参见 [`packages/backend/.env.example`](packages/backend/.env.example)。

## 数据存储与迁移

当前业务数据库均为 SQLite：主后端使用 `xiaoyi.db`，IoT 诊断使用 `iot_diagnosis.db`，IoT 控制使用 `iot_control.db`。知识向量同步到 Qdrant。项目不再提供 MySQL 连接、镜像同步、迁移或重建入口。

默认 Compose 项目名为 `last-work` 时，数据库位置如下；自定义项目名时，卷名前缀随之变化：

| 数据 | Compose 服务 | 容器内文件 | Docker 命名卷 |
| --- | --- | --- | --- |
| 用户、对话、模型配置与记忆 | `backend` | `/app/data/xiaoyi.db` | `last-work_backend-data` |
| 设备、历史遥测、日志、诊断与知识文档 | `iot-mcp` | `/app/data/iot_diagnosis.db` | `last-work_iot-mcp-data` |
| 控制命令、审批与执行结果 | `iot-mcp` | `/app/data/iot_control.db` | `last-work_iot-mcp-data` |

这些 SQLite 文件保存在 Docker 数据卷中，不在宿主机仓库目录下。Docker Desktop 可在对应容器的 **Files → app → data** 中查看，或在 **Volumes** 中查看命名卷。`/var/lib/docker/volumes/.../_data` 属于 Docker Desktop 的 Linux 环境，并非 Windows 文件路径。

Docker Desktop 中若仍显示已停止的 `last-work-mysql-1`，它是旧部署遗留容器，当前 Compose 和应用均不使用它；原有 `last-work_mysql-data` 卷不会自动迁入 SQLite。

主后端已启用 SQLite WAL 和写入等待超时；IoT 诊断与控制使用各自的 SQLite 连接配置，未显式开启 WAL。当前单机部署可继续使用 SQLite，多实例部署或持续写入竞争需要另行评估数据库方案。

后端迁移由部署命令按 Alembic 版本执行，基础 Compose 的容器启动流程会先迁移再启动应用。升级旧数据库时会清理已废弃的 workflow 表；历史 SQLite 与 Alembic 迁移保留，用于连续升级和 checksum 校验。

IoT MCP 的 SQLite 迁移通过 `python -m scripts.migrate upgrade --service diagnosis` 和 `python -m scripts.migrate upgrade --service control` 执行，基础 Compose 启动时自动运行。升级时直接删除旧故障案例与反馈表，并取消旧案例向量重试任务；官方文档、诊断和设备数据保留。向量重建使用 `rebuild_vector_index` 工具；旧 `scripts.rebuild_external` 命令已移除。

Compose 使用命名卷持久化业务数据库、MQTT 和 Qdrant 数据。普通 `docker compose down` 保留这些卷；`docker compose down -v` 会删除卷及其中的数据。

## 检索模型档位

### API 主模型 + 本地 Qwen 兜底

在根目录 `.env` 中配置主 Embedding / Reranker 的 provider、地址、模型、密钥及向量维度，并将 `DIAGNOSIS_LOCAL_EMBEDDING_FALLBACK` 和 `DIAGNOSIS_LOCAL_RERANKER_FALLBACK` 设为 `true`。字段模板见 [`.env.example`](.env.example)，协议与完整配置见 [API 检索配置](docs/retrieval-api.md)。已有 `.env` 时保留并修改其中配置。

```bash
docker compose -f compose.yaml -f compose.retrieval-api-fallback.yaml up -d --build
docker compose exec -T backend python scripts/bootstrap_local_mcp.py
```

Embedding 优先使用 API，失败后依次使用本地 Qwen3-Embedding-0.6B、hash；Reranker 按 API、本地 Qwen3-Reranker-0.6B、weighted 的顺序降级。每次新请求仍优先尝试 API，前端工具详情显示实际使用的模型与兜底状态。

API、本地和 hash 使用独立的 Qdrant 集合，不能混用向量。当前已验证的配置分别为 1024、512、384 维，API 维度须与实际模型输出一致。知识文档新增、替换和删除会同步维护各层索引；API 写入失败进入 outbox，恢复后自动补齐。本地模型写入失败期间 hash 仍更新，但本地索引需在服务恢复后手动补齐：

```bash
docker compose -f compose.yaml -f compose.retrieval-api-fallback.yaml exec -T iot-mcp python -m scripts.rebuild_fallback_indexes --target local
```

首次启用本地兜底也执行上述命令；`--target hash` 可重建 hash 索引，无需重复调用主 Embedding API。此档位默认从完整缓存离线加载本地模型，首次下载需在 `.env` 设置 `LOCAL_MODEL_CACHE_MODE=download`。更换主 Embedding 模型时使用新集合并调用 `rebuild_vector_index`；仅更换 Reranker 无需重建向量。

### 本地 Qwen 主模型 + Portable 兜底

Qwen3 模型服务没有放在默认 Compose 中，因为首次启动需要下载约 2.5 GiB 模型缓存，并占用约 2.6 GiB 显存；模型加载通常还需要 5–20 分钟。默认 Portable 档位使用 384 维 hash embedding，适合无 GPU、离线或快速开发环境。需要更强的语义检索时，再按下面的命令显式叠加模型档位。

在 Portable 档位之上叠加 `compose.retrieval-models.yaml`，把检索切换到本地 Docker 内的 Qwen3 模型服务：

```bash
docker compose -f compose.yaml -f compose.retrieval-models.yaml up -d --build
```

- **主档位**：`retrieval-models` 服务加载 `Qwen/Qwen3-Embedding-0.6B`（MRL 截断到 512 维）与 `Qwen/Qwen3-Reranker-0.6B`，向量写入主集合 `iot_diagnosis_qwen3_512`，检索继续走 hybrid（dense + BM25 + RRF + Qwen3 重排）。
- **兜底档位**：主集合与兜底集合独立，模型服务不可用时查询向量自动回落 hash（384 维）检索兜底集合 `iot_diagnosis_portable`，reranker 回落 weighted；服务恢复后 outbox 自动补齐主集合向量，无需人工干预。两个档位使用同一套检索代码，通过环境变量切换。
- **资源预期**：显存约 2.6 GiB（fp16，建议预留 4 GiB 以上），模型缓存约 2.5 GiB，首次冷启动 5–20 分钟。CPU-only 主机删除 `gpus: all` 即可，模型服务会自动回退 CPU 推理。
- **离线部署**：模型缓存完整后叠加 `compose.retrieval-offline.yaml`，缓存缺失时 `/ready` 返回 503 与 `MODEL_CACHE_INCOMPLETE`，不做网络下载。
- **切换与重建**：首次启用或主集合为空时，执行一次 `python -m scripts.ingest_recommended_documents` 或调用 `rebuild_vector_index` 工具重建主集合向量；兜底集合与 Portable 档位共用，已有数据直接可用。
- `DIAGNOSIS_EMBEDDING_FALLBACK=false` 可关闭兜底；`DIAGNOSIS_QDRANT_FALLBACK_COLLECTION`、`DIAGNOSIS_EMBEDDING_FALLBACK_DIMENSIONS` 可调整兜底集合与维度。

## 测试

前端命令统一在仓库根目录执行：

```bash
npm run typecheck
npm run lint
npm test
npm exec --workspace=packages/frontend -- playwright install chromium  # 首次运行端到端测试时安装浏览器
npm run test:e2e
```

后端与 MCP 服务分别在对应目录安装开发依赖后运行：

```bash
python -m pip install -e ../retrieval -e ".[dev]"
python -m pytest
```

前端测试使用 Vitest 和 Playwright；后端与 MCP 服务测试使用 pytest。Python 需要 3.12 或更高版本。

共享检索库的独立测试：在 `packages/retrieval` 中执行 `python -m pip install -e ".[dev]"` 和 `python -m pytest`。Docker 使用额外构建上下文自动安装共享库，需要支持 `additional_contexts` 的 Compose。直接构建镜像时也需传入 `--build-context retrieval=packages/retrieval`，示例见架构简化说明。

前后端联调冒烟（需先启动后端 8000 与前端 3000）：

```bash
python packages/backend/scripts/smoke_frontend_backend.py
```

默认通过前端同源代理验证就绪状态、登录 Cookie、CSRF 拒绝、会话 CRUD 与 SSE 对话全链路；测试消息固定 `tool_mode=none`，不调用设备工具，结束后清理临时对话。已保存的模型配置会覆盖 `AGENT_RUNTIME=mock`，因此普通冒烟的生成结果依赖该模型服务。加 `--api-base http://127.0.0.1:8000/api/v1` 可切换为跨域直连后端（要求 `FRONTEND_ORIGINS` 包含该前端来源）。

完整记忆浏览器联调使用独立前端 13000 和临时后端 18001，实际经过前端 `/api/backend` 代理、Cookie/CSRF、后端 SSE 与持久 worker。外部诊断和提炼采用确定性桩，不需要模型密钥。默认 `npm run test:e2e` 只运行原有会话流程，记忆流程需显式启用。Windows PowerShell 在仓库根目录执行：

```powershell
$env:E2E_MEMORY_LIVE = '1'
# 指向已安装 packages/backend[dev] 的 Python；使用现有可用虚拟环境即可
$env:E2E_PYTHON = (Resolve-Path 'packages/backend/.venv/Scripts/python.exe').Path
npm run test:e2e
Remove-Item Env:E2E_MEMORY_LIVE, Env:E2E_PYTHON
```

macOS/Linux 可用 `E2E_MEMORY_LIVE=1 E2E_PYTHON="$PWD/packages/backend/.venv/bin/python" npm run test:e2e`。测试会禁用 Wrangler 对 `.env.local` 的覆盖，并在发送消息前核验临时后端标记；不拦截或 mock 记忆 API 响应。运行前关闭同一前端目录已有的 dev 服务，Vinext 同一目录只允许一个 dev 实例。临时测试服务在结束后退出。

2026-10-07 IoT 工具可靠性修复后的验证：MCP 305 passed，后端 158 passed、1 skipped，前端 55 passed；类型检查、lint、构建和真实 MQTT 冒烟通过。后端、IoT MCP、模拟机群及前端已重启，控制库迁移到版本 5，工具目录与既定风险策略已刷新；前端页面、同源代理及两个服务的就绪检查均返回 HTTP 200。在线 MCP 调用验证了新动作枚举、六类动作验收说明、实时设备状态和 SQL 分页。测试边界与升级说明见 [IoT 工具可靠性说明](docs/iot-tool-reliability.md)。

2026-10-07 较早的 Text2SQL 与 API 检索联调验证：前端 54 passed，后端 158 passed、1 skipped，MCP 263 passed，浏览器基础流程 1 passed、真实 IoT / 知识库流程 2 passed；类型检查、lint 和构建通过。真实调用验证了 API、本地 Qwen、hash/weighted 及 API 恢复四条检索路径，知识文档新增、替换、删除同步到三套索引。启动步骤与验收细节见 [前后端联调说明](docs/integration-testing.md)。

真实 IoT 浏览器测试需要已启动的服务及有效模型配置，会调用外部模型 API。Windows PowerShell 在根目录运行：

```powershell
$env:E2E_IOT_LIVE = '1'
npm run test:e2e -- --workers=1 e2e/iot-live.spec.ts
Remove-Item Env:E2E_IOT_LIVE
```

2026-10-01 全项目清理后的验证（历史记录）：后端 162 passed、1 skipped，MCP 154 passed，共享检索库 10 passed，前端 Vitest 37 passed，完整浏览器流程 2 passed；类型检查、lint、构建、Compose 配置和 MCP wheel 内容核验均通过。清理与重启范围见 [全项目清理记录](docs/project-cleanup-20261001.md)。

2026-09-30 联调结果（历史记录）：

| 项目 | 实际结果 |
| --- | --- |
| 3000 → 同源代理 → 8000 | 登录、CSRF、会话 CRUD、SSE 通过，设备工具调用为零 |
| localhost:3000 → localhost:8000 | CORS 预检、凭据、会话 CRUD、SSE 通过 |
| 完整记忆浏览器流程 | 2 项 Playwright 通过，含既有会话流程；覆盖审核、409 版本冲突、新会话召回和 keep/forget |
| 后端回归 | 149 passed、1 skipped；真实 MCP 发现与动作工具新参数另行验证通过 |
| MCP 回归 | 150 passed、5 skipped（历史结果，当前存储与测试范围见上文） |
| 前端回归 | typecheck、lint、34 项 Vitest、build 全通过 |

首轮普通冒烟遇到外部模型流的连接中断；同源重验与跨域验证随后通过。确定性浏览器联调不依赖该外部模型。详细记忆验证与小样本在线语义评估见 [修复报告](docs/memory-repair-report-20260930.md)。

## 设备控制与恢复验证

低风险动作通过 `execute_device_action` 受理，高风险动作通过 `create_remediation_proposal` 提交并由人工审批。动作与提案均须关联真实诊断；`list_device_actions` 按服务已实现的 ESP32 设备协议筛选，并返回风险、参数 schema 和验收条件。

命令、审批与待投递记录原子落库。`ok=true` 表示请求已受理；`delivery_status` 区分待投递、发送中、Broker 确认、设备回执和结果未知。MQTT 暂时不可用时保留命令，通道恢复后继续发送；结果未知时不自动重发，队列有效期为 30 分钟。通过 `get_action_result` 查询设备执行及恢复验证结果。

恢复观察窗口按命令持久保存，服务重启后继续验证。MQTT 重连、WiFi 重连、传感器校准、上报间隔调整、设备重启和固件升级分别检查对应状态字段；仅设备在线不能证明修复成功。证据不足时返回 `verify_status=inconclusive`，前端显示“验证证据不足”，记忆模块按结果不明处理。真实设备需实现验收字段与过期命令拒绝，具体协议见 [可靠性与验收说明](docs/iot-tool-reliability.md)。

本次更新包含控制库迁移 0005 与工具参数 schema 变更。开发 Compose 启动时自动迁移；更新源码后重启后端、IoT MCP 和模拟机群，再运行 `bootstrap_local_mcp.py` 刷新工具与策略。宿主机前端单独重启，检索模型档位继续使用原有 Compose 覆盖文件。

## RAG + Text2SQL

聊天 Agent 现支持通过只读 MCP 工具 `query_iot_data`，用自然语言查询设备、历史遥测、日志和诊断摘要的统计、趋势、排名、明细及设备元数据关联。模型输出结构化查询计划，后端严格检查指标、聚合、时间与分组，并按固定模板生成 SQL；统计日志条数与去重设备数量使用各自的业务口径。技术资料继续使用现有文档 RAG；同时需要数据与解释时，Agent 先查 SQL 再检索文档，结合两类证据回答。

Text2SQL 复用 IoT MCP 的 `DIAGNOSIS_LLM_*` 配置，默认按北京时间解释日期，支持设备范围、只读视图、查询超时和结果截断。配置模型并更新服务后，重新运行 `bootstrap_local_mcp.py` 刷新工具及只读策略。仅配置前端聊天模型不会自动配置 MCP 的 SQL 生成模型。启用步骤、数据口径、执行边界和测试见 [Text2SQL 说明](docs/text2sql.md)。

例如在聊天中输入“统计过去 24 小时各节点平均温度和有效样本数”，展开 `query_iot_data` 查看结果表格、设备范围、时间窗口、SQL 和绑定参数。模型计划格式错误最多纠正一次；指标白名单、固定 SQL 模板、只读连接、超时和行数限制共同约束执行。设备范围冲突或业务口径不明确时要求澄清，不执行查询。

前端支持历史查询表格、检索 API/兜底状态及刷新后的工具结果恢复；启动方式和真实浏览器联调见 [前后端联调说明](docs/integration-testing.md)。

## 知识库分类

知识库按「设备与硬件」「网络与连接」「协议与通信」「平台与软件」展示，空分类自动隐藏。
原有 MQTT、WiFi、传感器和设备检索来源保留；展示领域独立保存，传感器与设备资料合并到硬件领域，
随项目提供的 OTA、日志、内存、事件循环等资料归入软件领域。已有资料无需重新摄取即可使用新分类。
上传文档可填写适用设备、文档类型、硬件版本和固件版本，标签保存在分块元数据中；列表支持搜索标题、文档 ID 和设备型号。
分类显示文档数量，分块数与字符数在「文档详情」中查看。现场案例与任务经验继续在「记忆」中管理。

## 记忆（Memory）

旧故障案例库与自动沉淀链路已整体退役，由主后端的记忆模块替代（设计见 [`docs/memory-replacement-spec.md`](docs/memory-replacement-spec.md)，历史验收证据见 [`docs/memory-repair-report-20260930.md`](docs/memory-repair-report-20260930.md)）。2026-09-30 复验发现的生命周期、来源清除与修复执行边界问题已修复，浏览器记忆流程与小型语义评估通过；正式部署和规模性能验证仍需另行执行。

- 三层记忆：工作记忆（会话内，不入向量）、情景记忆（一次具体经历，含成功/失败/无结论）、经验记忆（可复用认识与步骤）。同一会话的新 Run 会加载此前任务留下的工作记忆（TTL 默认 24 小时，`MEMORY_WORKING_TTL_HOURS`）。
- 自动提炼的经验一律先进入候选，用户在界面确认后才参与召回；情景中已收敛的事实性经历可直接作为历史参考。Agent 可用只读的 `search_memory` / `get_memory` 查询当前用户自己的记忆；`propose_memory` 只能创建待确认候选。
- 召回按用户隔离：Run 开始与 `diagnose_fault` 前两次注入，设备/状态查询等纯实时请求不加载历史经验。检索命中会记录使用阶段，但只有被实际采纳并执行的经验才按命令结果累计有效/无效反馈。
- 反例处理：具体动作以 `applied_memory_refs` 指定已检索、仍有效的经验版本，真实命令执行后才算采用；适用范围内明确失败会立即暂停并异步生成待确认修订。未知条件不算范围已匹配，超时不算明确失败；旧版本的晚到反例不暂停已重新确认的新版本。
- 修复预算：每个 Run 最多 3 次修复（`AGENT_REPAIR_MAX_ATTEMPTS`，部署时可降为 1–3，Run 创建时固化）；明确失败后自动重新诊断，需要新依据才继续，高风险动作逐次审批；超过运行期限（`AGENT_RUN_MAX_RUNTIME_MINUTES`，默认 60）后停止自动再诊断，结果由后台跟踪（最长 7 天）。
- 可观测性：`/metrics` 暴露 `memory.*` 生命周期事件、后台任务与 `remediation.loop_stopped`（含停止原因与已用名额）指标；`/api/v1/memories/activity` 返回候选数量、后台任务状态与命令结果追踪（含"需要后续诊断"标记）。
- REST 管理接口在 `/api/v1/memories`（列表/详情/编辑/确认/暂停/删除/检索/活动/失败任务重试），前端"记忆"入口展示认识、步骤、条件、限制、来源和版本对照，确认的是已查看的具体版本。编辑生成待确认新版本，旧版本继续召回；暂停版本重新确认前不可使用。晚到失败提供“发起后续诊断”入口，失败的记忆任务可手动重试。旧案例不迁入 memory。
- 旧案例 REST 接口（`/api/v1/fault-cases`、`/api/v1/diagnosis`）与 MCP 案例工具（`list_fault_cases` 等）已删除，调用返回 404；历史工具目录条目保持不可调用。
- 删除聊天默认保留长期记忆（`memory_policy=keep`）；勾选清除时撤回来源和受影响正文，多来源经验仅保留独立有效证据并重新审核。保留后也可从记忆详情清除已删除聊天的来源。删除的记忆正文按默认 30 天保留期由到期任务和周期扫描清理。
- 默认记忆检索使用 SQL 关键词降级。可通过共享的 `RETRIEVAL_QDRANT_URL`、`RETRIEVAL_EMBEDDING_BASE_URL`、`RETRIEVAL_EMBEDDING_MODEL`、`RETRIEVAL_EMBEDDING_DIMENSIONS` 和可选 API Key 配置模型连接；`MEMORY_*` 与 `DIAGNOSIS_*` 的对应专用配置优先，索引集合、记忆指纹和检索规则仍分别管理。单独启用 MCP 检索模型档位不会自动打开后端记忆向量配置；显式设置共享连接地址才会同时启用记忆向量。embedding 地址支持服务根地址及 `/v1` 基地址。Docker 地址使用 `http://qdrant:6333` 和 `http://retrieval-models:9010/v1`，宿主机使用 `127.0.0.1` 对应端口。共享配置与覆盖规则见 [架构简化说明](docs/architecture-simplification.md)。

## 常用维护命令

### 更新 Docker 服务

当前开发 Compose 将后端与 IoT MCP 的源码、脚本和迁移以只读方式挂载到容器。仅修改这些文件时，拉取代码后重启对应服务即可加载更新；容器启动命令会先执行数据库迁移：

```bash
git pull --ff-only
docker compose restart backend iot-mcp
docker compose exec -T backend python -m alembic current
docker compose ps
```

更新 Python 依赖、Dockerfile 或 Compose 配置时，需要重新构建并应用服务配置：

```bash
docker compose up -d --build backend iot-mcp
```

如果使用检索模型档位，维护命令继续带上原先使用的覆盖文件：API 主模型与本地兜底为 `-f compose.yaml -f compose.retrieval-api-fallback.yaml`，本地主模型为 `-f compose.yaml -f compose.retrieval-models.yaml`；离线档位也保留对应覆盖文件。修改 `.env` 或 Compose 配置后使用 `up -d` 重建容器配置，单纯 `restart` 不会更新环境变量。源码挂载加重启更新的是运行代码，不会改变镜像的构建时间。设备、知识和记忆数据保存在命名卷中。

### 前端重启、日志与停止

前端在运行 `npm run dev` 的终端按 `Ctrl+C` 停止，再执行 `npm run dev` 重启。更新前端依赖或锁文件后，先在根目录运行 `npm ci`。前端日志显示在该终端中。

Docker 服务的日志与停止：

```bash
docker compose logs -f backend iot-mcp
docker compose down
```

