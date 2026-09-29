# Xiaoyi IoT 平台

基于智能体和 MCP 的 IoT 设备诊断与控制平台。前端提供对话、知识文档和记忆管理界面；FastAPI 后端负责认证、对话、Agent 运行、工具策略与记忆管理；统一 IoT MCP 服务提供设备诊断、知识检索和设备控制能力。

## 当前架构

| 组件 | 目录或服务 | 职责 |
| --- | --- | --- |
| 前端 | `packages/frontend` | React 19 + Vinext，浏览器通过同源 `/api/backend` 代理访问后端 |
| 后端 | `packages/backend` | FastAPI、SQLite、Agent 运行、SSE、MCP 工具目录与审批策略 |
| IoT MCP | `packages/mcp-services/iot_mcp` | 单个 Streamable HTTP 服务，整合诊断与控制工具 |
| 基础设施 | `compose.yaml` | MQTT、Qdrant、设备模拟机群及后端和 MCP 容器 |

默认 Compose 使用本地 hash embedding 和 weighted reranker（Portable 档位），无需 GPU 或模型下载；需要真实语义检索时叠加检索模型档位（Qwen3 主档位，见下文「检索模型档位」），此时 hash + weighted 自动降级为兜底。后端默认使用演示 Runtime；若数据库中已保存模型配置，运行时会使用该配置。

运行状态由 Agent Run、运行事件和 SSE 事件流统一管理。平台不再维护独立的 IoT operation workflow 状态机、完成门或工作流详情接口；已有数据库升级到最新迁移时会自动删除旧的 workflow 数据表。

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

## 配置

- 后端本地运行配置参见 [`packages/backend/.env.example`](packages/backend/.env.example)。`AGENT_RUNTIME=mock` 可用于无模型密钥的联调；使用真实模型时配置模型 API 或相应环境变量。
- IoT MCP 的 Compose 环境变量位于 [`compose.yaml`](compose.yaml)。`DIAGNOSIS_LLM_API_KEY` 为可选项；默认 Portable 检索不依赖外部模型。
- 当前 `compose.yaml` 使用开发密钥、演示账号和本地端口绑定。生产部署须另行配置密钥、账号、数据库和 Cookie 策略，参见 [`packages/backend/.env.example`](packages/backend/.env.example)。

## 检索模型档位

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
python -m pip install -e ".[dev]"
python -m pytest
```

前端测试使用 Vitest 和 Playwright；后端与 MCP 服务测试使用 pytest。Python 需要 3.12 或更高版本。

数据库迁移会在后端启动流程中按 Alembic 版本执行。升级旧数据库时，迁移会清理已废弃的 workflow 表；历史迁移文件仍保留，用于保证已有数据库能够连续升级。

IoT MCP 的 SQLite/MySQL 镜像迁移通过 `python -m scripts.migrate upgrade` 执行。升级时直接删除旧故障案例与反馈表，并取消旧案例向量重试任务；官方文档、诊断和设备数据保留。

## 记忆（Memory）

旧故障案例库与自动沉淀链路已整体退役，由主后端的记忆模块替代（设计见 [`docs/memory-replacement-spec.md`](docs/memory-replacement-spec.md)，逐条验收证据见 [`docs/memory-acceptance-report.md`](docs/memory-acceptance-report.md)）：

- 三层记忆：工作记忆（会话内，不入向量）、情景记忆（一次具体经历，含成功/失败/无结论）、经验记忆（可复用认识与步骤）。同一会话的新 Run 会加载此前任务留下的工作记忆（TTL 默认 24 小时，`MEMORY_WORKING_TTL_HOURS`）。
- 自动提炼的经验一律先进入候选，用户在界面确认后才参与召回；情景中已收敛的事实性经历可直接作为历史参考。Agent 可用只读的 `search_memory` / `get_memory` 查询当前用户自己的记忆；`propose_memory` 只能创建待确认候选。
- 召回按用户隔离：Run 开始与 `diagnose_fault` 前两次注入，设备/状态查询等纯实时请求不加载历史经验。检索命中会记录使用阶段，但只有被实际采纳并执行的经验才按命令结果累计有效/无效反馈。
- 反例处理：被采用的经验在适用范围内明确失败时，立即暂停该经验并生成附反例说明的待确认修订；范围不匹配只记录范围问题。
- 修复预算：每个 Run 最多 3 次修复（`AGENT_REPAIR_MAX_ATTEMPTS`，部署时可降为 1–3，Run 创建时固化）；明确失败后自动重新诊断，需要新依据才继续，高风险动作逐次审批；超过运行期限（`AGENT_RUN_MAX_RUNTIME_MINUTES`，默认 60）后停止自动再诊断，结果由后台跟踪（最长 7 天）。
- 可观测性：`/metrics` 暴露 `memory.*` 生命周期事件、后台任务与 `remediation.loop_stopped`（含停止原因与已用名额）指标；`/api/v1/memories/activity` 返回候选数量、后台任务状态与命令结果追踪（含"需要后续诊断"标记）。
- REST 管理接口在 `/api/v1/memories`（列表/详情/编辑/确认/暂停/删除/检索/活动），前端"记忆"入口支持筛选、确认、编辑（生成待确认新版本，旧版本继续召回）与删除。旧案例不迁入 memory；新记忆只来自此后记录的任务或用户输入。
- 旧案例 REST 接口（`/api/v1/fault-cases`、`/api/v1/diagnosis`）与 MCP 案例工具（`list_fault_cases` 等）已删除，调用返回 404；历史工具目录条目保持不可调用。
- 删除聊天默认保留长期记忆（`memory_policy=keep`）；勾选清除时同事务写入来源抑制标记并暂停派生经验。

## 常用维护命令

```bash
docker compose logs -f backend iot-mcp
docker compose down
```

