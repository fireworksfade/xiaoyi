# 小yi 系统可靠性与可维护性详细实施计划 v1.0

- 状态：Draft
- 日期：2026-09-13
- 输入规格：`system-reliability-maintainability-improvement-spec-v1.0.md`
- 适用仓库：主仓库 `D:/last-work`、独立 MCP 仓库 `D:/last-work/mcp-services`
- 实施原则：小步提交、先兼容后切换、迁移与业务代码分离、每个阶段可独立验证和回滚

## 1. 计划目标

本计划把改进规格拆成 14 个可交付工作包。实施顺序优先消除发布阻断项，再治理数据增长和
长对话，最后补齐运维能力和代码边界。

完成后应达到：

1. 新环境、空模型缓存、无 GPU 和离线缓存四种部署路径都有确定行为。
2. Agent 任务在后端重启后必然收敛，不再永久卡住。
3. IoT 状态、遥测、日志、附件、Session、运行事件和 outbox 都有生命周期。
4. MCP 服务选择、设备元数据和时间语义正确。
5. 长对话、附件和流式事件有预算与分页。
6. 三套数据库具有正式迁移版本。
7. liveness、readiness、结构化日志、指标和 CI 可支持长期运维。

## 2. 实施约束

- 本计划不修改认证授权模型，也不设计多 worker 并行执行。
- Agent Dispatcher 首版只支持单进程、单执行器；多实例调度另立规格。
- 现有 REST 路径、MCP 工具名和成功信封保持兼容。
- 所有删除型保留策略先以 dry-run 上线，至少观察一个发布周期后再启用实际删除。
- 主仓库与 MCP 仓库分别提交；跨仓库接口变化必须先发布兼容接收方。
- 不以删除 Docker 数据卷作为任何正式迁移步骤。
- 每个工作包必须包含代码、测试、文档和回滚说明，不能只交付代码。

## 3. 技术决策

### 3.1 部署档位

采用三个显式入口：

| 档位 | 命令 | 检索实现 | 宿主要求 |
| --- | --- | --- | --- |
| Portable | `docker compose up -d --build` | hash embedding + weighted reranker | Docker，无 GPU |
| GPU | `docker compose -f compose.yaml -f compose.retrieval-gpu.yaml up -d --build` | Qwen3 embedding/reranker | NVIDIA runtime、足够显存和模型磁盘 |
| GPU offline | GPU 命令再叠加 `compose.retrieval-offline.yaml` | 已缓存 Qwen3 | 完整模型缓存，不允许下载 |

基础 `compose.yaml` 不声明 `gpus: all`，Diagnosis 默认使用本地确定性检索。GPU override 新增
`retrieval-models` 服务，并覆盖 Diagnosis 的 embedding/reranker/collection 配置和依赖。

### 3.2 Agent 任务执行

采用“数据库持久状态 + 单进程 Dispatcher + 周期扫描”的实现：

- API 事务提交 `QUEUED` 任务。
- `RunDispatcher.notify(run_id)` 只负责降低启动延迟，不是唯一执行保证。
- Dispatcher 每秒扫描一次 `QUEUED` 任务并按创建时间执行。
- 启动恢复把旧 `RUNNING` 标记为 `FAILED/RUN_INTERRUPTED`；不自动重放。
- 本版不实现多进程任务认领、分布式锁和并行 worker。

### 3.3 数据库迁移

- 主后端使用 Alembic，并采用 async SQLAlchemy 官方模板。
- Diagnosis 和 Control 使用轻量 SQLite migration runner：
  `schema_migrations(version, name, applied_at, checksum)` 加有序 Python migration 模块。
- Repository 构造阶段只验证版本，不继续新增内联 `ALTER TABLE`。
- 外部 MySQL schema 由独立有序 migration 管理，不在普通读写路径动态建表。

### 3.4 消息游标

使用不透明 URL-safe Base64 游标，编码 `{created_at, id}`。查询按
`created_at DESC, id DESC` 取最近一页，返回前反转成升序。游标实现集中放在通用分页模块，
前端不得解析游标内容。

### 3.5 上下文预算

首版采用保守估算器，不绑定特定模型 tokenizer：

- ASCII 连续文本按约 4 字符/token。
- 非 ASCII 字符按约 1.5 字符/token。
- 消息结构和角色每条增加固定开销。

设置 `AGENT_CONTEXT_MAX_INPUT_TOKENS`，默认 60,000；同时保持消息数和附件字符硬上限。
后续可通过 `TokenEstimator` 接口增加模型专用实现。

### 3.6 运行事件

采用 `RunEventBuffer`：

- `answer.delta` 累积到 256 字符或 200 ms 后形成一个事件。
- 语义事件到达时先刷新已有 delta，再立即入批次。
- 每批使用一次事务和一次 flush，不逐事件 refresh。
- 工具输出 JSON 持久化上限默认 64 KiB；超限保存摘要、原大小和 SHA-256。

### 3.7 可观测性

- 日志使用 Python 标准库自定义 JSON formatter，避免额外日志框架绑定。
- 指标采用 `prometheus-client`；FastAPI/MCP 服务暴露 `/metrics`。
- `/live` 和 `/ready` 分离；原 `/health` 暂时保留兼容并明确其语义。

## 4. 工作包和依赖总览

| ID | 工作包 | 仓库 | 依赖 | 建议规模 |
| --- | --- | --- | --- | --- |
| WP-01 | 建立基线与 CI 骨架 | 两者 | 无 | M |
| WP-02 | 模型缓存和部署档位 | 主仓库、MCP | WP-01 | M |
| WP-03 | 后端 Alembic 基线 | 主仓库 | WP-01 | M |
| WP-04 | Agent Dispatcher 和重启收敛 | 主仓库 | WP-03 | L |
| WP-05 | MCP SQLite/MySQL 迁移框架 | MCP | WP-01 | L |
| WP-06 | 设备当前状态和元数据修复 | MCP | WP-05 | L |
| WP-07 | 遥测、日志和 outbox 生命周期 | MCP | WP-06 | L |
| WP-08 | 移除启动全量同步 | MCP | WP-05 | M |
| WP-09 | MCP 能力路由 | 主仓库 | WP-03 | M |
| WP-10 | 上下文预算和消息分页 | 主仓库、前端 | WP-03 | L |
| WP-11 | 附件、Session 和事件生命周期 | 主仓库、前端 | WP-04、WP-10 | L |
| WP-12 | liveness、readiness、日志和指标 | 两者 | WP-04、WP-07、WP-08 | L |
| WP-13 | 前端组件与 E2E 覆盖 | 主仓库 | WP-09、WP-10、WP-11 | L |
| WP-14 | 模块拆分、发布演练和文档收口 | 两者 | 全部 | L |

规模含义：S 为 1 个小变更集，M 为 2–3 个变更集，L 为 3–6 个变更集；不作为日历承诺。

## 5. WP-01：建立基线与 CI 骨架

### 5.1 目标

在改 schema 和运行机制前固定现有行为，确保两个仓库能独立测试。

### 5.2 主仓库任务

新增或修改：

- `.github/workflows/main-ci.yml`
- `backend/pyproject.toml`
- `frontend/package.json`
- `frontend/vitest.config.ts`
- `frontend/test/setup.ts`
- `README.md`

任务：

1. 后端 CI 安装 `backend[dev]`，执行格式检查、lint、类型检查和 pytest。
2. 前端增加 `test`、`typecheck`、`format:check` 脚本。
3. 引入 Vitest、Testing Library、jsdom，并创建一个 API 客户端 smoke test。
4. 保留现有 build 命令作为必过门槛。
5. 将跨仓库的 Agents SDK Streamable HTTP 测试移动到
   `backend/tests/integration/test_mcp_transport.py`。

### 5.3 MCP 仓库任务

新增或修改：

- `mcp-services/.github/workflows/ci.yml`
- `mcp-services/pyproject.toml`
- `mcp-services/tests/test_http_connection.py`
- `mcp-services/README.md`

任务：

1. 移除 MCP 测试对 `app.mcp_http` 和 `agents.mcp` 的跨仓库导入。
2. MCP 协议测试使用本仓库声明的 `mcp` SDK，或移动到主后端后删除重复测试。
3. 新建干净虚拟环境执行 `pip install -e ".[dev]" && pytest`。
4. 增加 Ruff 配置；类型检查可先从新模块开始，不要求一次修完全部旧代码。

### 5.4 验收

- 主仓库 CI 在无 Docker、无 GPU 环境通过单元测试和前端构建。
- MCP CI 在自身虚拟环境中完成收集并通过，不引用主仓库路径。
- 当前后端 24 项和 MCP 78 项核心行为不退化。
- CI 产出测试报告，并对失败命令给出准确退出码。

### 5.5 回滚

CI 文件可独立回滚；依赖清单变更不影响生产镜像依赖。

## 6. WP-02：模型缓存和部署档位

### 6.1 文件级改动

修改：

- `compose.yaml`
- `mcp-services/Dockerfile.models`
- `mcp-services/model_service/app.py`
- `README.md`
- `mcp-services/README.md`

新增：

- `compose.retrieval-gpu.yaml`
- `compose.retrieval-offline.yaml`
- `mcp-services/model_service/cache.py`
- `mcp-services/model_service/errors.py`
- `mcp-services/scripts/check_model_cache.py`
- `mcp-services/tests/test_model_cache.py`

### 6.2 实施步骤

1. 从基础 Compose 移除强制 `gpus: all` 和无条件 `HF_HUB_OFFLINE=1`。
2. 基础 Diagnosis 环境改为 hash embedding、weighted reranker 和独立的 384 维 collection。
3. GPU override 定义 `retrieval-models`、Qwen3 配置、1024 维 collection 和健康依赖。
4. Offline override 只设置 cache mode，不直接依赖 Hugging Face 的模糊异常。
5. 模型服务启动时先执行缓存清单检查：模型目录、config、tokenizer 和权重至少存在一套完整文件。
6. `download` 模式缺失时允许下载；`offline` 模式缺失时抛出领域错误并记录结构化状态。
7. `/live` 在加载期间可响应；`/ready` 显示 `loading/ready/failed`。
8. Docker 健康检查由 `/health` 改为 `/ready`。
9. 文档列出显存、磁盘、首次下载和离线准备步骤。

### 6.3 测试

- 单测：完整缓存、缺 embedding、缺 reranker、离线缺失、下载模式。
- 容器测试：空测试卷 download；填充后 offline；空卷 offline 快速失败。
- Portable smoke：不安装 NVIDIA runtime，核心服务全部就绪。
- GPU smoke：仅在有 GPU runner 或发布机器执行最小 embedding/rerank。

### 6.4 发布与回滚

- 先发布 Portable 行为，GPU 保持通过 override opt-in。
- 若 GPU override 失败，可回滚 override，不影响 Portable。
- 不删除现有 `retrieval-model-cache`；旧缓存可直接验证后复用。

## 7. WP-03：主后端 Alembic 基线

### 7.1 文件级改动

新增：

- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/script.py.mako`
- `backend/migrations/versions/0001_current_schema.py`
- `backend/migrations/versions/0002_run_recovery_fields.py`
- `backend/app/cli.py`
- `backend/tests/migrations/test_upgrade_snapshots.py`
- `backend/tests/fixtures/db/README.md`

修改：

- `backend/pyproject.toml`
- `backend/app/db.py`
- `backend/app/main.py`
- `backend/Dockerfile`
- `compose.yaml`

### 7.2 实施步骤

1. 生成与当前模型一致的 0001 基线迁移，包括现有 `deleted_at`。
2. 对已有库采用 stamp 策略：验证关键表/列后标记 0001；空库正常 upgrade。
3. 0002 增加运行恢复字段和必要索引。
4. 删除 `create_schema()` 中的手写 `ALTER TABLE`；开发初始化统一走 `alembic upgrade head`。
5. 容器启动命令拆为迁移步骤和应用步骤；单实例 Compose 可使用 entrypoint 顺序执行。
6. 应用启动只检查 schema revision，不自行修改 schema。
7. schema ahead 时 readiness 返回 `DATABASE_SCHEMA_AHEAD`。

### 7.3 测试

- 空库升级到 head。
- 当前生产形态快照 stamp + upgrade。
- 重复执行 upgrade 无变化。
- 从 0001 升 0002 后已有 run 数据不变。
- schema ahead 拒绝 ready。
- downgrade 至少验证最近一个 additive migration；无法无损降级时明确标注 forward-only。

### 7.4 回滚

- 0002 只新增可空列，旧应用可忽略。
- 首次发布不立即删除 `create_schema` 代码，可保留一个版本但默认禁用；确认后再移除。

## 8. WP-04：Agent Dispatcher 和重启收敛

### 8.1 文件级改动

新增：

- `backend/app/services/run_dispatcher.py`
- `backend/app/services/run_recovery.py`
- `backend/app/services/run_state.py`
- `backend/tests/test_run_dispatcher.py`
- `backend/tests/test_run_recovery.py`

修改：

- `backend/app/main.py`
- `backend/app/api/router.py`，后续移动到 `api/messages.py`
- `backend/app/services/runs.py`
- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/config.py`

### 8.2 Dispatcher 生命周期

1. FastAPI lifespan 创建 `RunDispatcher(SessionFactory, process_agent_run)`。
2. 启动顺序：检查迁移 → 恢复扫描 → 启动 Dispatcher → seed 开发数据 → ready。
3. `submit_message` 提交后调用 `request.app.state.run_dispatcher.notify(run.id)`。
4. Dispatcher 按 FIFO 扫描 `QUEUED`，调用原有处理函数。
5. 处理开始设置 `started_at`、`last_progress_at`、`attempt_count += 1`。
6. 每次持久化语义事件时更新 `last_progress_at`。
7. 完成/失败写 `finished_at`。
8. 优雅停止先停止取新任务；当前任务在宽限期内完成，超时则写
   `RUN_INTERRUPTED` 后取消。

### 8.3 恢复扫描

在 Dispatcher 启动前：

- 查询全部 `RUNNING`，逐条写 `run.failed` 和 `RUN_INTERRUPTED`。
- 保持并重新通知全部 `QUEUED`。
- 修复只有终态状态但缺终态事件的旧数据。
- 输出恢复计数日志和指标。

### 8.4 API 和前端契约

`RunView.error.retryable` 对 `RUN_INTERRUPTED` 返回 true。首版新增：

- `POST /agent-runs/{id}/retry`

重试创建新的 user message/run，或复用原始输入但生成新的 run ID；不得把旧 run 从 FAILED
改回 QUEUED。重试 API 的具体授权沿用现有用户所有权规则，不在本计划调整安全模型。

### 8.5 测试

- 提交后通知丢失，周期扫描仍执行任务。
- QUEUED 重启恢复。
- RUNNING 重启转中断。
- graceful shutdown 成功和超时两条路径。
- 异常为 `CancelledError` 时仍写终态。
- retry 产生新 run，旧 run 保持不可变。
- SSE 在恢复事件发完后结束。

### 8.6 回滚

- 保留新增列不回退。
- 可用配置 `RUN_DISPATCHER_MODE=legacy` 临时切回 BackgroundTasks 一个发布周期；切回时
  启动扫描仍必须执行，避免遗留状态。

## 9. WP-05：MCP SQLite/MySQL 迁移框架

### 9.1 文件级改动

新增：

- `mcp-services/common/migrations.py`
- `mcp-services/iot_diagnosis/migrations/0001_current.py`
- `mcp-services/iot_diagnosis/migrations/0002_state_lifecycle.py`
- `mcp-services/iot_control/migrations/0001_current.py`
- `mcp-services/iot_diagnosis/mysql_migrations/`
- `mcp-services/scripts/migrate.py`
- `mcp-services/tests/test_migrations.py`
- `mcp-services/tests/fixtures/db/README.md`

修改：

- `mcp-services/iot_diagnosis/repository.py`
- `mcp-services/iot_control/repository.py`
- `mcp-services/iot_diagnosis/external.py`
- 两个 server 的启动生命周期

### 9.2 Migration runner 要求

- 在事务中执行单个 migration。
- migration 文件包含不可变 version/name/checksum。
- 已应用版本 checksum 变化时拒绝启动。
- 支持 `status`、`upgrade`、`dry-run`、`backup` 命令。
- SQLite backup 使用官方 backup API 写入显式目标文件。
- 普通 Repository 创建不运行 migration，只验证 head。

### 9.3 基线策略

1. 0001 能从空库创建当前 schema。
2. 对已有库验证关键表后 stamp 0001。
3. 把现有动态列补丁固化到 0001/兼容检测中。
4. 0002 承载第 10 节的 current state、received time 和 telemetry schema。
5. Control 当前 schema 同样纳入 0001，移除初始化内联 ALTER。

### 9.4 测试与回滚

- 空库、当前快照、缺一个历史列、重复升级、checksum 不一致。
- migration 中途失败后版本号不前进。
- 每个数据变换 migration 都准备前后计数断言。
- 发布前备份，失败时停止新版本并恢复备份；不在失败库上反复试错。

## 10. WP-06：设备当前状态和元数据修复

### 10.1 新 schema

`device` 增加：

- `updated_at`

新增 `device_current_state`：

- `device_id` PK/FK
- `online`
- `wifi_status`
- `rssi`
- `mqtt_status`
- `temperature`
- `uptime`
- `device_timestamp`
- `received_at`
- `last_event_kind`
- `payload_hash`

新增 `device_telemetry`：

- `id`
- `device_id`
- 测量字段
- `device_timestamp`
- `received_at`
- `payload_hash`
- 唯一索引 `(device_id, device_timestamp, payload_hash)`
- 查询索引 `(device_id, received_at DESC)`

### 10.2 Repository API

把 `upsert_status` 拆为：

- `apply_status(device_id, payload, received_at)`
- `append_telemetry(device_id, payload, received_at)`
- `touch_heartbeat(device_id, payload, received_at)`
- `upsert_device_metadata(device_id, payload, received_at)`

`get_device_status` 只查询 `device + device_current_state`，不再扫描历史表。在线 freshness 使用
`received_at`。

### 10.3 MQTT 映射

- `/status`：更新 current state 和元数据；只有明确配置时才采样一条 telemetry。
- `/telemetry`：追加历史测量并用较新的 received_at 合并 current state。
- `/heartbeat`：只更新 last seen/online/uptime，不复制整行历史状态。
- `/logs`、`/fault`：保持日志路径，但统一增加 received_at。

### 10.4 存量迁移

1. 为每个设备按 `timestamp DESC, id DESC` 选最新一行建立 current state。
2. 旧 timestamp 解析失败时保存原值，received_at 使用迁移时间并记录异常计数。
3. 旧 `device_status` 暂时重命名为 `device_status_legacy`，不立即删除。
4. 新代码切读 current state、切写新表。
5. 观察一个发布周期后由 WP-07 处理 legacy 历史。

### 10.5 元数据规则

- `name/device_type/firmware_version` 非空才覆盖。
- `unknown` 不覆盖已有非 unknown 值。
- 实际值可以覆盖 unknown。
- 元数据变化更新 `updated_at`；无变化不改。

### 10.6 测试

- status、telemetry、heartbeat 分流。
- 相同 telemetry 去重。
- heartbeat 先于 status 的新设备。
- firmware/name 更新。
- 空/unknown 字段不回退已有值。
- 设备时钟正负偏移、无时区、非法 timestamp。
- `list_devices` 使用单条集合查询消除 N+1，并在 SQL 层过滤和分页。

### 10.7 回滚

新表 additive，旧表保留；可在一个版本内通过配置切回 legacy 读路径。切回前禁止清理 legacy。

## 11. WP-07：遥测、日志和 outbox 生命周期

### 11.1 文件级改动

新增：

- `mcp-services/iot_diagnosis/retention.py`
- `mcp-services/scripts/retention.py`
- `mcp-services/tests/test_retention.py`

修改：

- `mcp-services/iot_diagnosis/server.py`
- `mcp-services/iot_diagnosis/repository.py`
- `mcp-services/iot_diagnosis/external.py`
- `compose.yaml`
- `.env.example`

### 11.2 配置

增加：

- `DIAGNOSIS_TELEMETRY_RETENTION_DAYS=14`
- `DIAGNOSIS_INFO_LOG_RETENTION_DAYS=14`
- `DIAGNOSIS_ERROR_LOG_RETENTION_DAYS=90`
- `DIAGNOSIS_RECORD_RETENTION_DAYS=180`
- `DIAGNOSIS_OUTBOX_COMPLETED_RETENTION_DAYS=7`
- `DIAGNOSIS_RETENTION_INTERVAL_HOURS=6`
- `DIAGNOSIS_RETENTION_BATCH_SIZE=1000`
- `DIAGNOSIS_RETENTION_DELETE_ENABLED=false`

### 11.3 实施步骤

1. `retention --dry-run` 输出每类候选数、最早/最晚时间和预计释放空间。
2. 清理按主键分页，每批独立提交，避免超长事务。
3. INFO/DEBUG 与高等级日志使用不同截止日期。
4. diagnosis 已被 fault case 关联时保留；未建立显式关联的旧数据先不删。
5. 只删除 `completed_at` 非空且已过期的 outbox。
6. 外部 MySQL 运行同等清理，失败进入单独运维错误，不反向删除本地更多数据。
7. 后台周期任务只在 `DELETE_ENABLED=true` 时执行删除；否则持续报告 dry-run 指标。
8. legacy status 完成去重/聚合后，由显式命令清理，不由普通周期任务直接删除。

### 11.4 容量验收

- 12 台模拟设备运行 24 小时，heartbeat 不增加 telemetry 行。
- 相同 status/telemetry 载荷不重复。
- 7 天 soak 中数据库日增长稳定且符合配置采样率。
- 保留期缩短的测试库可分批收敛，进程峰值内存稳定。

### 11.5 发布与回滚

1. 第一版只上线 dry-run 和指标。
2. 观察至少一个完整保留任务周期。
3. 手工备份并审阅候选计数。
4. 打开删除开关。
5. 若计数异常，关闭开关；已删除数据仅通过备份恢复。

## 12. WP-08：移除启动全量同步

### 12.1 文件级改动

新增：

- `mcp-services/iot_diagnosis/rebuild.py`
- `mcp-services/scripts/rebuild_external.py`
- `mcp-services/tests/test_rebuild_external.py`

修改：

- `mcp-services/iot_diagnosis/repository.py`
- `mcp-services/iot_diagnosis/server.py`
- `mcp-services/README.md`

### 12.2 实施步骤

1. 从 `DiagnosisRepository.__init__` 删除 `retry_external_sync()` 和
   `_sync_external_snapshot()`。
2. server lifespan 启动独立 outbox retry loop；首次 retry 不扫描事实表。
3. 把 `_sync_external_snapshot` 拆成可分页、可恢复的显式 rebuild 服务。
4. 每种实体使用稳定游标：status/log 用递增 id，document/case/diagnosis 用稳定主键。
5. 进度写入单独 `rebuild_job` 表，记录 entity、cursor、processed、failed 和状态。
6. Qdrant 重建使用新 collection 临时名，完成验证后再切换配置或 alias；切换机制不在普通启动执行。
7. readiness 显示 outbox backlog，但显式 rebuild 运行本身不必让服务不就绪。

### 12.3 测试

- 100 万 status fixture 的 Repository 构造不全表读取。
- rebuild 每页最多读取配置条数。
- 中断后从 cursor 继续。
- 重复执行不会增加重复 MySQL/Qdrant 业务记录。
- 外部失败时 job 保留准确 cursor 和错误。

### 12.4 回滚

显式 rebuild 是新增能力；若增量同步出现问题，可以手工运行 rebuild，不能恢复成每次启动全量扫描。

## 13. WP-09：MCP 能力路由

### 13.1 文件级改动

新增：

- `backend/app/services/mcp_capabilities.py`
- `backend/tests/test_mcp_capability_routing.py`

修改：

- `backend/app/api/knowledge.py`
- `backend/app/api/fault_cases.py`
- `backend/app/api/diagnosis.py`
- `backend/app/api/remediation.py`
- `backend/app/services/mcp_catalog.py`
- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/scripts/bootstrap_local_mcp.py`

### 13.2 实现接口

新增：

```python
async def resolve_mcp_server(
    db: AsyncSession,
    *,
    required_tools: set[str],
    explicit_server_id: str | None = None,
    default_key: str | None = None,
) -> MCPServer:
    ...
```

匹配条件同时包含：服务启用、connected、未删除、工具已发现、工具启用，以及当前调用要求的
risk policy。调用方显式声明 required tools，不再共享“取最老 IoT 服务”的函数。

### 13.3 配置和数据

- 可选增加 `service_kind` 和 `is_default_for_kind`；通过 Alembic additive migration。
- bootstrap 为 diagnosis/control 写稳定 kind。
- 若现有数据库没有 kind，先从稳定 server key 和工具能力推导，不能依赖 name。

### 13.4 测试

- Control 先创建、Diagnosis 后创建。
- Diagnosis 删除重建。
- 两个服务拥有相同能力。
- 显式 service ID 能力不匹配。
- 工具存在但 disabled。
- 工具 risk policy 不符合写入要求。
- catalog 未刷新和 server disconnected。

### 13.5 前端影响

前端 API 错误字典增加：

- `MCP_CAPABILITY_UNAVAILABLE`
- `MCP_CAPABILITY_MISMATCH`
- `MCP_CAPABILITY_AMBIGUOUS`

歧义时设置页引导管理员配置默认服务；普通用户只看到可操作的不可用说明。

## 14. WP-10：上下文预算和消息分页

### 14.1 后端文件级改动

新增：

- `backend/app/services/context_builder.py`
- `backend/app/services/token_estimator.py`
- `backend/app/api/conversations.py`
- `backend/app/pagination.py`
- `backend/tests/test_context_builder.py`
- `backend/tests/test_message_pagination.py`

修改：

- `backend/app/services/runs.py`
- `backend/app/api/router.py`
- `backend/app/config.py`
- `backend/app/schemas.py`

### 14.2 ContextBuilder 算法

1. 查询当前消息及向前最多 100 条候选历史，不先加载整段对话。
2. 把 user/assistant 配对为轮次；当前未完成 user 单独保留。
3. 从当前向旧轮次累加估算 token。
4. 附件只在所属消息被选中时考虑，并受单附件/总字符限制。
5. 预算不足时先把旧附件替换为占位，再移除最旧轮次。
6. 不允许截断当前用户文本；若当前文本自身超过预算，运行以
   `CONTEXT_INPUT_TOO_LARGE` 失败并提供限制信息。
7. 构建结果写入 `AgentRun.runtime_state.context`，不污染用户消息。

### 14.3 消息分页查询

- 后端 SQL 按复合游标查询，不用 offset 扫描长历史。
- `limit` 默认 50、最大 200。
- 响应增加 `next_cursor/has_more`，保留 `items`。
- 不传参数时返回最近一页，这是有意的行为变化，必须在同一发布更新前端。

### 14.4 前端文件级改动

新增：

- `frontend/hooks/use-conversation-messages.ts`
- `frontend/components/message-list.tsx`

修改：

- `frontend/lib/api.ts`
- `frontend/app/page.tsx`

实现：

- 初次加载最近 50 条。
- 顶部“加载更早消息”使用 next cursor。
- prepend 后保持滚动锚点，避免页面跳动。
- 对话切换取消旧分页状态。
- 新消息追加不清空已加载历史。

### 14.5 测试

- 相同 timestamp 使用 id 稳定翻页，无重复/遗漏。
- 500 条消息翻完后顺序完全一致。
- 当前消息始终进入上下文。
- 附件占位与省略计数准确。
- 中文、英文和混合文本估算边界。
- 前端加载更早消息保持滚动位置。

### 14.6 回滚

后端可通过 `MESSAGE_PAGINATION_LEGACY_DEFAULT=true` 暂时恢复全量默认一个版本；前端仍兼容
分页字段。ContextBuilder 可通过配置放宽限制，但不得重新采用无界加载。

## 15. WP-11：附件、Session 和事件生命周期

### 15.1 文件级改动

新增：

- `backend/app/services/retention.py`
- `backend/app/services/run_event_buffer.py`
- `backend/app/api/attachments.py` 中的删除端点实现或独立 service
- `backend/app/cli.py` 的 retention 子命令
- `backend/tests/test_retention.py`
- `backend/tests/test_run_event_buffer.py`

修改：

- `backend/app/services/runs.py`
- `backend/app/api/attachments.py`
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/models.py`
- `frontend/lib/api.ts`
- `frontend/app/page.tsx`

### 15.2 附件回收

- 新增 `DELETE /attachments/{id}`，仅删除未绑定附件。
- 前端从草稿移除附件时调用删除；失败不阻塞 UI，但记录待后台回收。
- retention 清理 `message_id IS NULL` 且超过 24 小时的行。
- 记录原始 size 与 extracted chars；清理指标分别统计。

### 15.3 Session 回收

- 删除 `expires_at < now - grace_period` 的 Session。
- 登录或鉴权发现过期 Session 时可以安排惰性删除，但周期清理仍是最终保证。
- 默认每 6 小时运行一次，每批 1,000 行。

### 15.4 RunEventBuffer

1. 为每个 run 创建 buffer。
2. 合并 answer delta。
3. 语义事件刷新 delta 并按原顺序追加。
4. `append_events(run_id, events)` 一次事务写多行并更新 progress。
5. 工具输出超过 64 KiB 时调用 `summarize_event_payload`，保存：
   `truncated=true/original_bytes/sha256/summary`。
6. run 终态前强制 flush。
7. 失败路径也强制 flush 已有事件，再写 run.failed。

### 15.5 终态压缩

- assistant message 成功持久化是删除 delta 的前置条件。
- 完成 24 小时后删除该 run 的 `answer.delta`，保留 run.started、工具摘要、提案、
  run.completed/failed。
- 压缩任务写 `runtime_state.events_compacted_at`。
- 未完成/失败且没有最终消息的 delta 按更长的可配置诊断期保留，默认 7 天。

### 15.6 测试

- 2,000 delta 合并阈值。
- flush timer、字符阈值、语义事件顺序和异常路径。
- 超大工具 JSON 的摘要/哈希可重复。
- 压缩前后最终消息一致。
- 未绑定附件和过期 Session 分批删除。
- dry-run 不修改任何行。

### 15.7 回滚

- 第一版 retention 默认 dry-run。
- EventBuffer 可配置为 flush 每事件用于故障回退，但仍使用批量 API；不能恢复逐事件 refresh。

## 16. WP-12：liveness、readiness、日志和指标

### 16.1 公共探针契约

所有 Python 服务返回：

```json
{
  "status": "ready|degraded|not_ready|alive",
  "service": "...",
  "version": "...",
  "checks": {
    "component": {"status": "ok|degraded|failed", "error_code": null}
  }
}
```

HTTP 状态：live 固定 200；ready 在必需组件失败时 503，只有可选组件失败时 200 degraded。

### 16.2 后端实施

新增：

- `backend/app/observability/logging.py`
- `backend/app/observability/metrics.py`
- `backend/app/services/readiness.py`
- `backend/tests/test_readiness.py`

检查：数据库 SELECT 1、schema revision、Dispatcher running。MCP 只检查声明为 required 的服务。

### 16.3 MCP 和模型服务实施

新增公共 JSON formatter 和指标 helper，两个 MCP 分别检查本地库版本、MQTT 状态、outbox、
已配置外部存储。模型服务检查缓存和已加载模型。

### 16.4 错误分类

建立 `AppError`/`RunError` 映射表：

- `CONFIGURATION_ERROR`
- `VALIDATION_ERROR`
- `DEPENDENCY_UNAVAILABLE`
- `RUN_INTERRUPTED`
- `DATABASE_SCHEMA_BEHIND`
- `DATABASE_SCHEMA_AHEAD`
- `MODEL_CACHE_INCOMPLETE`

每类明确 HTTP 状态、公开 message、retryable 和日志级别。`process_agent_run` 保留内部异常链，
不再只存 `str(exc)`。

### 16.5 指标实现顺序

1. HTTP 请求和延迟。
2. run 状态和耗时。
3. MCP 调用和延迟。
4. outbox/retention/数据库体积。
5. context budget/event compaction。
6. model load/inference。

避免在请求时对大表执行 `COUNT(*)`；数据库规模指标由周期采样器更新。

### 16.6 Compose 改动

- backend healthcheck 改 `/ready`。
- Diagnosis/Control healthcheck 改 `/ready`。
- 模型 healthcheck 改 `/ready`。
- `depends_on` 只表达实际必需组件。
- 文档说明 `docker compose ps` healthy 的精确含义。

### 16.7 测试

- 每个依赖单独失败的 probe matrix。
- required 与 optional MCP。
- schema ahead/behind。
- Dispatcher 未启动。
- 指标端点 smoke 和关键 counter 增长。
- 日志字段完整性和 request/run/trace ID 贯通。

## 17. WP-13：前端组件与 E2E 覆盖

### 17.1 组件拆分顺序

从 `page.tsx` 先提取无状态展示，再提取 hooks：

1. `MessageList` 和 `MessageItem`。
2. `MessageComposer`。
3. `ConversationSidebar`。
4. `useConversationList`。
5. `useConversationMessages`。
6. `useConversationRun`。
7. `useAttachmentDraft`。

每次提取保持现有页面行为，不把视觉改版混入重构 PR。

### 17.2 API/SSE 单元测试

覆盖：

- 标准成功和错误信封。
- 204、非 JSON、断流和无效 JSON SSE。
- 多个 `data:` 行、CRLF、chunk 边界、最后无空行事件。
- run.failed、RUN_INTERRUPTED 和正常完成。
- 消息游标分页。
- capability 三类错误。

SSE parser 应从 `api.ts` 提取为纯函数/异步迭代器，以便不依赖真实网络测试。

### 17.3 组件测试

- 首屏 loading/empty/error。
- 乐观 user message 与流式 assistant message。
- 中断后重试。
- 加载更早消息保持滚动。
- 附件移除调用后端 delete。
- 提案刷新后恢复。
- 对话切换时旧请求结果不污染新对话。

### 17.4 E2E

新增：

- `frontend/playwright.config.ts`
- `frontend/e2e/conversation.spec.ts`
- `frontend/e2e/run-recovery.spec.ts`
- `frontend/e2e/attachments.spec.ts`
- `frontend/e2e/mcp-routing.spec.ts`

使用后端 mock runtime 和临时 SQLite。每个测试独立初始化数据库。重启恢复测试由测试脚本启动、
停止并重新启动后端进程，断言 UI 最终状态。

### 17.5 门槛

- 关键 hooks 和 API transport 分支覆盖率目标 85%。
- 全局覆盖率首版不作为阻断，防止用低价值测试填数字。
- 四条关键 E2E 全部阻断合并。

## 18. WP-14：模块拆分、发布演练和文档收口

### 18.1 后端拆分

将 `backend/app/api/router.py` 拆为：

- `api/auth.py`
- `api/conversations.py`
- `api/messages.py`
- `api/runs.py`
- `api/router.py` 只聚合子路由

将 run 逻辑保持在 service 层，API 不直接操作事件缓冲和恢复扫描。

### 18.2 Diagnosis 拆分

把 `repository.py` 拆为：

- `repositories/base.py`
- `repositories/devices.py`
- `repositories/logs.py`
- `repositories/knowledge.py`
- `repositories/diagnoses.py`
- `repositories/outbox.py`

保留一个 facade `DiagnosisRepository` 组合这些 repository，避免一次修改全部调用点。

### 18.3 文档收口

更新：

- 根 README 快速启动矩阵。
- backend README 的 migration、dispatcher、retention、probe 命令。
- MCP README 的 Portable/GPU/offline、migration、rebuild、retention 命令。
- 故障排查：模型缓存不完整、schema ahead、outbox 积压、run interrupted。
- 发布清单和回滚清单。

### 18.4 发布演练

在隔离项目名和测试卷上执行：

1. 当前版本写入代表性数据。
2. 备份三个 SQLite。
3. 升级新镜像并执行迁移。
4. 验证对话、运行、设备、知识、案例和提案。
5. 运行 24 小时 soak。
6. 验证 retention dry-run。
7. 重启 backend/Diagnosis/Control/model service。
8. 验证所有任务和 outbox 收敛。
9. 执行回滚演练：旧应用读取 additive schema，或恢复备份。

## 19. 数据迁移详细顺序

### 19.1 发布前

1. 停止写入窗口或进入维护模式。
2. 记录镜像 commit、数据库 revision、各表行数和文件大小。
3. 分别备份 backend、Diagnosis、Control SQLite。
4. 验证备份可打开且关键表可查询。

### 19.2 主后端

1. Stamp/upgrade 0001。
2. Upgrade run recovery fields。
3. 启动新后端，恢复扫描收敛旧 RUNNING。
4. 验证历史对话、消息、run 和审计记录数量。
5. retention 保持 dry-run。

### 19.3 Diagnosis

1. Stamp/upgrade MCP 0001。
2. 创建 current state 和 telemetry 新表。
3. 从 legacy 状态构建每设备最新快照。
4. 切换新代码写路径。
5. 核对每台设备当前状态、固件版本和 last seen。
6. 运行 legacy 去重 dry-run。
7. 至少观察一个发布周期后才清理 legacy。

### 19.4 Control

1. Stamp/upgrade 0001。
2. 验证 pending proposal、command 和 case link。
3. 不改变现有状态机数据。

### 19.5 外部存储

1. 先升级 MySQL schema。
2. 验证增量 outbox 正常。
3. 不在应用启动时全量同步。
4. 仅在计数不一致时运行显式 rebuild。
5. Qdrant collection 维度变化使用新 collection，不原地混写。

## 20. 测试矩阵

| 层级 | Portable | GPU | Offline | 旧数据升级 | 重启 | 长对话 | Retention |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 单元测试 | 必须 | 模型逻辑 mock | 必须 | migration 函数 | 状态函数 | 预算算法 | 截止日期/批次 |
| API/MCP 集成 | 必须 | 可选 runner | 必须 | 必须 | 必须 | 必须 | dry-run 必须 |
| Compose smoke | 必须 | 发布前必须 | 发布前必须 | 必须 | 必须 | 可选 | dry-run |
| E2E | 必须 | 不需要 | 不需要 | 代表快照 | 必须 | 必须 | 不需要 |
| Soak | 7 天候选版 | 24 小时 | 4 小时 | 使用升级库 | 周期重启 | 500+ 消息 | 启用删除 |

关键失败注入：

- 空模型缓存。
- 模型缓存缺一个文件。
- 数据库 schema ahead/behind。
- Agent QUEUED/RUNNING 时重启。
- MySQL/Qdrant 暂时不可用。
- 设备时间漂移和非法时间。
- 重复 MQTT 载荷。
- SSE 中途断开和无效事件。
- 超大工具输出、长对话和附件预算耗尽。
- retention 中途失败后重新运行。

## 21. 性能与容量门槛

| 指标 | 基线/问题 | 目标 |
| --- | --- | --- |
| Diagnosis 本地初始化 | 随全库线性增长 | 100 万 status fixture 下 ≤10 秒且不全表镜像 |
| 状态写入 | 每周期可写 3 条等价状态 | heartbeat 0 条历史；重复样本 0 条 |
| list devices | 全量加载 + N+1 | SQL 过滤分页，查询次数不随设备数线性增长 |
| Agent delta 事务 | 接近 delta 数 | 2,000 delta ≤100 次事件事务 |
| 消息首屏 | 全历史 | 默认 ≤50 条 |
| Agent 输入 | 无界 | ≤配置 token/消息/附件预算 |
| outbox completed | 永久保留 | 默认 7 天收敛 |
| 未绑定附件 | 永久保留 | 默认 24 小时收敛 |

性能测试使用固定数据集和硬件说明，报告 P50/P95、数据规模和峰值内存，不能只报告单次最好值。

## 22. 发布策略

### 22.1 发布 1：基础设施

包含 WP-01、WP-02、WP-03、WP-05。只引入 CI、部署档位和迁移框架，不开启删除。

Go 条件：

- 空卷 Portable/GPU download/offline 行为全部符合预期。
- 三套当前数据库快照升级通过。

### 22.2 发布 2：运行可靠性和能力路由

包含 WP-04、WP-09。

Go 条件：

- 重启演练中无永久运行状态。
- Diagnosis/Control 注册顺序交换后全部业务路由通过。

### 22.3 发布 3：IoT 数据治理

包含 WP-06、WP-08、WP-07 dry-run。

Go 条件：

- current state 与 legacy 最新值逐设备一致。
- 启动不执行全量同步。
- retention 候选数量经人工核对。

### 22.4 发布 4：长对话和事件治理

包含 WP-10、WP-11，事件压缩可开启，删除型 retention 仍按独立开关控制。

Go 条件：

- 500 条消息分页和上下文预算 E2E 通过。
- 最终 assistant 内容与压缩前一致。

### 22.5 发布 5：运维收口

包含 WP-12、WP-13、WP-14，并在备份后逐步开启 retention 删除。

Go 条件：

- 7 天 soak 无持续增长异常。
- probe/metrics/告警演练通过。
- 发布和回滚 runbook 由非作者执行成功。

## 23. 回滚策略

### 23.1 应用回滚

- 所有 schema 变更先 additive，至少保持旧应用可读一个发布周期。
- 不在引入新读路径的同一发布删除旧列/旧表。
- 通过 feature flags 控制 Dispatcher legacy 通知、current state 读路径、分页默认和 retention 删除。

### 23.2 数据回滚

- 迁移前备份是强制门槛。
- 数据变换失败优先停止新版本并恢复备份。
- retention 删除后的恢复只来自备份，不承诺逻辑逆操作。
- Qdrant 使用新 collection/alias 切换，回滚时切回旧 collection。

### 23.3 部署回滚

- Portable 与 GPU override 分离；GPU 故障不影响 Portable。
- 模型缓存不随容器回滚删除。
- Offline 缓存校验失败时回到 download 模式，不绕过完整性检查。

## 24. 风险登记

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 旧 timestamp 格式不统一 | current state 迁移错误 | 解析异常单独计数，保留原值，逐设备核对 |
| Legacy 状态量大 | 迁移耗时、磁盘临时翻倍 | 分批迁移、预估空间、延后删旧表 |
| 运行中断涉及已调用工具 | 自动重放产生重复业务动作 | RUNNING 只标记 interrupted，不自动重放 |
| GPU 模型首次下载时间长 | Compose 长时间 starting | loading 状态、长 start period、文档化下载量 |
| 上下文截断改变回答质量 | 长对话信息缺失 | 记录省略元数据、保留最近完整轮次、后续可加摘要 |
| 工具输出截断影响排障 | 缺少完整事件正文 | 保存摘要/大小/哈希，业务结果留在事实源 |
| Retention 配置错误 | 误删历史 | 默认 dry-run、备份、候选审阅、独立 delete flag |
| 两个独立仓库版本漂移 | 协议不匹配 | 固定 commit 集成任务、兼容接收方先发布 |
| 模块拆分引入回归 | UI/API 行为变化 | 重构后置、一次一边界、E2E 先行 |

## 25. 实施检查清单

每个工作包合并前：

- [ ] 关联本计划中的 WP 和验收条目。
- [ ] 新 schema 有 migration，不在初始化路径临时修改。
- [ ] 新配置有默认值、校验、`.env.example` 和 README。
- [ ] 成功、失败、恢复和边界测试齐全。
- [ ] 新后台任务支持关闭、dry-run 或清晰终态。
- [ ] 日志包含 service/event/error code 和可用关联 ID。
- [ ] 指标不在请求路径扫描大表。
- [ ] 兼容旧数据库和旧 API 消费方。
- [ ] 有明确回滚步骤。
- [ ] `git diff --check`、lint、typecheck、tests、build 全部通过。

## 26. 最终完成标准

只有同时满足以下条件，整体计划才可标记完成：

1. WP-01 至 WP-14 全部满足各自验收。
2. 改进规格第 4–12 节的验收项有自动化证据。
3. Portable、GPU download、GPU offline 三套启动路径验证通过。
4. 后端在 QUEUED 和 RUNNING 两个时点的重启演练都能收敛。
5. 当前数据卷完成无损迁移，设备当前状态抽样与迁移前一致。
6. 12 台模拟设备 7 天 soak 的日增长符合保留策略。
7. 500 条消息、多附件、超大工具输出场景通过预算、分页和压缩验收。
8. 两个仓库可在各自干净环境独立通过 CI。
9. 所有容器探针、结构化日志和核心指标可被实际读取。
10. 发布、备份、迁移、恢复、rebuild、retention 和回滚文档由非实现者复跑成功。
