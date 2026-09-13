# 小yi 系统可靠性与可维护性改进规格 v1.0

- 状态：Draft
- 日期：2026-09-13
- 适用范围：`frontend/`、`backend/`、`mcp-services/`、`compose.yaml`
- 基线：当前主仓库与 IoT MCP 仓库实现
- 关联规格：`iot-diagnosis-mcp-completion-spec-v1.1.md`、`iot-diagnosis-mcp-discovery-spec-v1.3.md`、`iot-control-mcp-spec-v1.0.md`

## 1. 目的

本规格解决当前系统在部署可复现性、任务恢复、数据生命周期、设备状态正确性、
服务发现、上下文治理、事件存储、数据库演进、可观测性和自动化验证方面的问题。

交付完成后，系统必须具备以下结果：

1. 全新检出代码和空数据卷可以按文档启动，不依赖机器上已有模型缓存。
2. 后端重启不会让 Agent 运行永久停留在 `QUEUED` 或 `RUNNING`。
3. 遥测、日志、运行事件、会话和 outbox 都有明确的数据保留与清理策略。
4. 设备名称、类型和固件版本随有效状态上报更新。
5. MCP 业务请求按能力选择服务，不依赖服务创建顺序。
6. 长对话和大附件不会无限扩大模型输入、API 响应和数据库体积。
7. 数据库变更可版本化、测试、审计和回滚。
8. 健康检查能区分进程存活与业务就绪，故障可以通过统一日志和指标定位。
9. 三个子系统都能在自己的依赖环境中完成测试，关键用户链路有自动化覆盖。

## 2. 范围

### 2.1 必须完成

- 检索模型冷启动和无 GPU 环境的部署配置。
- Agent 运行的中断收敛和恢复契约。
- IoT 状态快照、遥测历史、日志和 outbox 的生命周期管理。
- 设备元数据更新和服务端接收时间记录。
- MCP 能力路由。
- 对话上下文预算、消息分页和附件回收。
- Agent 流式事件合并、压缩和保留策略。
- 后端与两个 MCP 服务的版本化数据库迁移。
- liveness、readiness、日志、指标和错误分类。
- 前端测试、仓库自包含测试、CI 和冷启动验收。
- 对超大职责文件进行边界拆分。

### 2.2 不在本规格范围

- 认证、授权、密钥管理或其他安全模型调整。
- 多 worker 竞争、锁策略、并行调度吞吐量或其他并发控制设计。
- 新的诊断算法、Embedding 模型、Reranker 模型或设备控制动作。
- 业务 UI 视觉重设计。
- 将 SQLite、MySQL 或 Qdrant 替换为其他产品。

现有安全与并发行为不得因本规格产生有意变化；涉及这些边界的实现应另立规格。

## 3. 优先级和兼容性

### 3.1 优先级

| 优先级 | 工作项 | 阻断条件 |
| --- | --- | --- |
| P0 | 空卷模型启动、任务中断收敛 | 阻断可用版本发布 |
| P1 | 遥测生命周期、设备元数据、启动全量同步、能力路由 | 阻断生产试运行 |
| P1 | 上下文预算、事件压缩、正式迁移 | 阻断长时间运行 |
| P2 | 就绪检查、指标、前端/E2E/CI、代码拆分 | 阻断正式运维交接 |

### 3.2 兼容性规则

- 已存在的 REST 路径和 MCP 工具名称保持兼容；新增分页字段必须向后兼容。
- REST 成功信封继续使用 `{data, request_id}`；MCP 信封继续使用
  `{ok, data, error, trace_id}`。
- 已完成的 `AgentRun`、对话、知识文档、故障案例和控制提案不得丢失。
- 数据保留策略首次启用前必须提供 dry-run 统计，并允许运维人员执行一次备份。
- 迁移不得要求删除现有 Docker 命名卷。
- 前端可以逐步采用新字段，但后端不能在同一版本中直接删除旧字段。

## 4. 可复现部署与检索模型冷启动

### 4.1 模型缓存模式

检索模型服务必须支持两个显式模式：

- `download`：允许从配置的模型源下载缺失文件，下载完成后写入持久卷；这是全新环境的默认模式。
- `offline`：禁止网络下载，仅在模型缓存完整时启动；缓存缺失时快速失败并给出
  `MODEL_CACHE_INCOMPLETE`，不得停留在无说明的重启循环。

不得在基础 Compose 中无条件设置 `HF_HUB_OFFLINE=1`。离线模式应通过独立 override、
profile 或显式环境变量启用。

服务启动前必须检查两个模型的必要文件。检查结果至少包括：

- `embedding_model_cached`
- `reranker_model_cached`
- `cache_mode`
- `loading_stage`
- `last_error_code`

### 4.2 CPU/GPU 部署档位

- 基础开发档位不得因为宿主机没有 NVIDIA runtime 而使整套 Compose 无法启动。
- GPU 检索模型通过 `retrieval-gpu` profile 或独立 Compose override 启用。
- 无 GPU 档位可以选择 CPU 模型服务或诊断服务已有的确定性 hash/weighted fallback；
  选定行为必须写入 README，且 `/ready` 必须真实反映当前档位。
- GPU 档位必须记录所需显存、磁盘空间、首次下载量和预期冷启动时间。

### 4.3 健康语义

- `/live`：进程事件循环可响应即返回 200。
- `/ready`：模型均加载且可执行最小推理才返回 200。
- 模型下载或加载期间 `/ready` 返回 503 和 `status=loading`。
- 模型加载失败时返回稳定错误码，不返回 Python 堆栈给调用方。

### 4.4 验收

1. 删除测试专用命名卷后，在有网络、无预置缓存的环境执行标准启动命令，模型服务最终就绪。
2. 在空缓存的 offline 模式启动，60 秒内得到 `MODEL_CACHE_INCOMPLETE`。
3. 在无 NVIDIA runtime 的 CI 主机执行基础档位，除明确标记为 GPU profile 的服务外全部就绪。
4. 下载完成后重启 offline 模式，不产生网络下载并能成功推理。
5. README 命令与 Compose 默认行为一致。

## 5. Agent 运行持久化与中断收敛

### 5.1 状态模型

保留 `QUEUED → RUNNING → COMPLETED | FAILED` 主状态机，并增加以下持久字段：

- `queued_at`
- `started_at`
- `finished_at`
- `last_progress_at`
- `attempt_count`
- `interruption_reason`

本规格不定义多 worker 抢占或并行调度；实现以单执行器语义为准。

### 5.2 提交与执行

- 消息和 `AgentRun(QUEUED)` 必须在同一数据库事务中提交。
- HTTP 202 只表示任务已持久化，不表示内存回调一定存活。
- 运行触发必须封装为 `RunDispatcher` 接口，API 层不得直接依赖 FastAPI
  `BackgroundTasks` 作为唯一执行保证。
- Dispatcher 在应用生命周期内启动，在优雅关闭时停止接收新任务，并收敛当前任务状态。

### 5.3 重启恢复

启动时必须执行一次恢复扫描：

- `QUEUED`：重新交给 Dispatcher。
- `RUNNING`：转换为 `FAILED`，错误码 `RUN_INTERRUPTED`，`retryable=true`，写入
  `run.failed` 事件。
- 已终态任务保持不变。

不得自动重放已经进入 `RUNNING` 的任务，以免重复执行外部工具；是否重试由独立用户操作决定。

### 5.4 SSE 收敛

- SSE 在任务进入终态且所有已提交事件发送完后关闭。
- `RUN_INTERRUPTED` 必须能被现有事件流消费者识别。
- 事件流不得因为数据库里遗留的 `RUNNING` 状态而无限保持。
- 前端刷新后必须能从运行详情或消息历史显示中断原因和可重试状态。

### 5.5 验收

1. 在 `QUEUED` 状态强制停止后端，重启后任务被重新执行并进入终态。
2. 在 `RUNNING` 状态强制停止后端，重启后 10 秒内任务变成
   `FAILED/RUN_INTERRUPTED`，SSE 正常结束。
3. 终态任务重启前后不变化，不新增重复 assistant message。
4. 现有 `client_message_id` 幂等行为保持通过。

## 6. IoT 数据模型与生命周期

### 6.1 分离最新快照与历史序列

将当前所有 status/telemetry/heartbeat 都写入 `device_status` 的行为拆分为：

- `device_current_state`：每个设备一行，使用 upsert 保存最新可查询状态。
- `device_telemetry`：仅保存需要分析的历史测量值。
- `device_heartbeat` 不单独保存完整状态，只更新 `last_seen_at` 和必要的在线字段。
- `device_log`：保存日志和 fault 归一化事件。

`status` 和内容相同的 `telemetry` 在同一上报周期不得形成重复历史样本。去重键至少包含
`device_id + event_kind + device_timestamp + payload_hash`。

### 6.2 时间语义

每条输入同时保留：

- `device_timestamp`：设备声明时间，可为空或不可信。
- `received_at`：服务端收到消息的 UTC 时间，必填。

在线判断和数据保留基于 `received_at`，展示和诊断可以同时使用设备时间。设备时间漂移不得让
设备永久在线或立即误判离线。

### 6.3 设备元数据

状态上报包含非空 `name`、`device_type` 或 `firmware_version` 时必须更新设备表，而不是
`INSERT OR IGNORE` 后永久保留首次值。

- 缺失字段不得覆盖已有值。
- 固件升级后的下一帧状态必须能在 `get_device_status` 中看到新版本。
- `updated_at` 记录最后一次元数据变化时间。

### 6.4 默认保留策略

| 数据 | 默认保留期 | 到期动作 |
| --- | --- | --- |
| 原始 telemetry | 14 天 | 删除；可选保留小时级聚合 |
| INFO/DEBUG 日志 | 14 天 | 删除 |
| WARNING/ERROR/CRITICAL 日志 | 90 天 | 删除或归档 |
| diagnosis records | 180 天 | 可配置删除；已关联案例不受影响 |
| 已完成 outbox | 7 天 | 删除 |
| 未完成 outbox | 不自动删除 | 持续暴露积压与最后错误 |
| 过期 Session | 7 天宽限期 | 删除 |
| 已完成 Agent 原始增量事件 | 24 小时 | 压缩后删除，见第 9 节 |
| 未绑定附件 | 24 小时 | 删除 |

所有保留期必须可配置。清理任务必须分页执行，并输出扫描数、删除数、耗时和失败数。

### 6.5 存量数据迁移

- 迁移前输出各表行数、时间范围和预计删除/聚合数量。
- 从 `device_status` 为每个设备构建最新快照。
- 对相同设备、相同时间、相同载荷的历史状态去重。
- 迁移成功并验证计数后才允许清理旧表。
- 提供 dry-run 和可重复执行的迁移命令。

### 6.6 验收

1. 12 台模拟设备运行 24 小时，历史样本数量不超过配置采样频率的 110%。
2. 同周期 status、telemetry、heartbeat 不产生三条等价状态记录。
3. 模拟 `update_firmware` 后，下一次 `get_device_status` 返回新版本。
4. 设备时间分别偏移正负 24 小时，在线判断仍按实际接收时间正确工作。
5. 清理任务重复运行结果稳定，且不删除未完成 outbox 和故障案例。

## 7. 外部存储同步与启动性能

### 7.1 正常启动

- Repository 构造函数只完成轻量配置和本地 schema 检查，不执行全库外部同步。
- 正常启动只处理未完成 outbox，不扫描全部 status、logs、documents 或 diagnoses。
- 已完成 outbox 按第 6.4 节清理。

### 7.2 显式重建

全量同步改为独立管理命令，至少支持：

- `rebuild-mysql --entity <type> --batch-size N --resume-from CURSOR`
- `rebuild-qdrant --source <source> --batch-size N --resume-from CURSOR`
- `--dry-run`

命令必须分页读取、输出进度和恢复游标；失败后可从上次游标继续，不得一次将全表加载到内存。

### 7.3 增量同步

- 正常写入继续使用稳定业务键进行 upsert。
- outbox 状态报告增加最老待处理时间 `oldest_pending_at` 和最后成功时间
  `last_delivery_at`。
- 失败次数达到配置阈值后仍不丢弃，但必须在 readiness/metrics 中明确显示。

### 7.4 验收

1. 构造含 100 万 status、10 万 logs 的测试库，服务启动期间不执行全量镜像调用。
2. 不包含模型加载时，诊断服务进程在 10 秒内完成本地初始化。
3. 全量重建进程峰值内存不随总行数线性增长。
4. 中断重建后使用游标继续，最终外部记录数与本地事实源一致。

## 8. MCP 服务能力路由

### 8.1 能力标识

`purpose=iot` 只用于粗分类，不得作为知识、诊断或控制服务的唯一选择依据。

主后端必须根据已发现且启用的工具目录匹配业务所需能力：

- 知识读取：`list_knowledge_documents`
- 知识写入：`ingest_knowledge_text`、`delete_knowledge_document`
- 故障案例：`list_fault_cases`、`delete_fault_case` 或 `add_verified_fault_case`
- 控制审批：`decide_remediation_proposal`

可以增加持久字段 `service_kind`，取值 `diagnosis | control | generic`，但运行时仍必须验证
所需工具存在且策略符合调用要求。

### 8.2 选择规则

1. 请求显式提供 `service_id` 时，验证该服务具备所需能力；否则返回
   `MCP_CAPABILITY_MISMATCH`。
2. 未提供时，仅有一个匹配服务则选择它。
3. 没有匹配服务返回 `MCP_CAPABILITY_UNAVAILABLE`。
4. 多个匹配服务且没有配置默认值时返回 `MCP_CAPABILITY_AMBIGUOUS`，不得按创建时间静默选择。

### 8.3 验收

- 先注册 Control、后注册 Diagnosis，知识和案例 API 仍选择 Diagnosis。
- 删除并重建 Diagnosis 后路由结果不变化。
- 注册两个都带同一能力的服务时，未配置默认项的请求返回明确歧义错误。
- 显式传入不具备目标工具的服务时不向远端发起调用。

## 9. 对话上下文、附件和运行事件治理

### 9.1 上下文构建器

从 `process_agent_run` 中提取独立的 `ContextBuilder`，负责：

- 按模型配置确定最大输入预算。
- 始终保留当前用户消息。
- 从新到旧选择历史轮次，不能拆开一组 user/assistant 语义轮次。
- 在预算不足时优先省略旧附件正文，再省略旧消息。
- 向运行元数据记录 `included_message_count`、`omitted_message_count`、
  `included_attachment_chars` 和估算 token 数。

默认限制：

- 最大历史消息：100 条。
- 最大估算输入：模型上下文上限的 70%，且保留输出和工具调用空间。
- 单附件进入模型的文本：50,000 字符。
- 单次运行所有附件正文：100,000 字符。

限制必须可配置。超限附件保留文件名和“正文因预算被省略”的占位说明。

### 9.2 消息分页

`GET /conversations/{id}/messages` 增加游标分页：

- `limit` 默认 50、最大 200。
- `before` 表示读取更早消息。
- 返回 `items`、`next_cursor`、`has_more`。
- 默认返回最近一页，同时维持页面内时间升序。

前端初次只加载最近消息，并提供“加载更早消息”。不得一次下载完整长对话。

### 9.3 附件生命周期

- 未绑定附件按第 6.4 节自动回收。
- 对话软删除后，附件随对话数据保留策略处理。
- 上传成功但发送失败时，前端可显式删除附件；即使未删除，后台回收也必须生效。
- 清理结果进入统一指标。

### 9.4 流式事件合并与压缩

- `answer.delta` 在写库前按 100–250 ms 或最小字符阈值合并，具体值可配置。
- 一批事件使用一次事务提交；不得为每个 token/delta 单独 commit 和 refresh。
- `tool.started`、`tool.finished`、提案语义事件和终态事件必须保留顺序。
- 工具完整输出设置持久化大小上限；超限时保存摘要、字节数和内容哈希，完整结果由业务事实源保存。
- 任务完成 24 小时后，将 delta 压缩成最终 assistant message，并删除可重建的原始 delta。
- 终态事件和错误摘要保留，确保运行记录仍可解释。

### 9.5 验收

1. 生成超过模型上下文上限的对话，运行仍能提交且元数据准确报告省略量。
2. 500 条消息的对话首屏最多读取配置的一页。
3. 10 MB 附件上传后不发送，超过保留期会被清理。
4. 模拟 2,000 个 delta，数据库事务数显著低于 delta 数，目标不超过 100 次。
5. 事件压缩后 assistant 最终内容不变，SSE 不再依赖已删除的过期 delta。

## 10. 数据库迁移体系

### 10.1 主后端

- 使用 Alembic 或等价版本化迁移工具管理 SQLAlchemy schema。
- 生产启动不得使用 `Base.metadata.create_all()` 代替迁移。
- 开发环境可以提供显式 `db init`，但结果必须与迁移到最新版本一致。

### 10.2 MCP 服务

- Diagnosis 和 Control 各自维护线性迁移版本表和迁移脚本。
- 禁止继续在 Repository 初始化中散落新的 `PRAGMA table_info + ALTER TABLE`。
- 每个迁移具有版本、描述、升级步骤、兼容性说明和回退方案。

### 10.3 启动规则

- 数据库版本落后时，由部署步骤先迁移；服务不得边接收业务请求边修改 schema。
- 数据库版本高于当前代码支持版本时拒绝就绪，错误码 `DATABASE_SCHEMA_AHEAD`。
- 迁移失败时保持旧版本可识别，不得把版本号提前标记为成功。

### 10.4 迁移测试

至少保留以下快照 fixture：

- 当前发布版主后端 SQLite。
- 当前 Diagnosis SQLite。
- 当前 Control SQLite。
- 含大量重复 `device_status` 的数据生命周期迁移库。

CI 对每个快照执行升级、数据断言、重复执行检查和应用启动检查。

## 11. 可观测性和健康检查

### 11.1 后端探针

- `/live` 仅验证进程存活。
- `/ready` 至少验证数据库 `SELECT 1`、迁移版本、Dispatcher 状态。
- 如果当前部署把特定 MCP 声明为必需依赖，readiness 同时报告其目录状态；非必需 MCP
  故障作为 degraded，不阻止后端提供对话历史。
- 原 `/health` 保持兼容，但文档和容器健康检查必须明确其语义。

### 11.2 结构化日志

后端、Diagnosis、Control 和模型服务统一输出 JSON 或可机器解析日志，公共字段包括：

- `timestamp`
- `level`
- `service`
- `event`
- `request_id`
- `run_id`、`trace_id`、`device_id`（存在时）
- `duration_ms`
- `error_code`

Agent 失败必须记录异常类别和内部堆栈，同时对客户端继续返回稳定的公共错误结构。

### 11.3 指标

至少提供以下指标：

- HTTP 请求量、错误量和延迟。
- Agent queued/running/completed/failed 数量与运行时长。
- SSE 当前连接数和持续时间。
- 各 MCP 调用数量、错误率和延迟。
- telemetry/log 每分钟写入量和清理量。
- 各数据表近似行数或存储字节数。
- outbox pending、oldest pending age、delivery failures。
- 模型加载状态、embedding/rerank 请求量和延迟。
- 上下文估算 token、被省略消息和附件字符数量。

### 11.4 错误分类

错误至少区分：

- 配置错误：不可重试。
- 参数/业务状态错误：不可自动重试。
- 外部服务暂时不可用：可重试。
- 任务中断：可由用户重试。
- 数据库 schema 不兼容：运维处理后重试。

不得把所有 Agent 失败统一标记为 `retryable=false`。

## 12. 测试与持续集成

### 12.1 仓库自包含

- 主后端测试只依赖 `backend[dev]` 声明的包。
- MCP 测试只依赖 `mcp-services[dev]` 声明的包，不得导入主后端的 `app.*`。
- 当前使用 `agents.mcp` 和 `app.mcp_http` 的跨仓库传输测试应移动到主后端集成测试，
  或改写为只使用 MCP 仓库自己的 SDK。
- 每个 README 中的测试命令必须能在对应仓库新建的虚拟环境中直接运行。

### 12.2 前端测试

至少增加：

- API 客户端：成功信封、标准错误、非 JSON 响应、SSE 分块和无效事件。
- 页面状态：首次加载、空对话、发送消息、运行失败、刷新后恢复。
- 消息分页和“加载更早消息”。
- 附件上传、移除、发送失败和后台过期后的显示。
- MCP 能力歧义与不可用错误展示。
- 修复提案卡刷新恢复。

关键前后端链路使用 Playwright 或等价 E2E：登录、创建对话、发送、接收流、重命名、
删除、刷新恢复。

### 12.3 CI 门槛

主仓库 CI：

1. Python lint/format/type check。
2. 后端单元与 API 测试。
3. 前端 lint、format check、TypeScript、组件测试、生产构建。
4. 数据库迁移快照测试。
5. 使用 mock runtime 的前后端 E2E。

MCP 仓库 CI：

1. Python lint/format/type check。
2. Diagnosis、Control、Simulator 单元测试。
3. Repository 迁移和生命周期测试。
4. 使用确定性模型的 MCP 协议测试。
5. 可选 GPU 模型 smoke，不能阻塞普通提交 CI，但必须阻塞 GPU 发布物。

发布前集成任务使用固定的主仓库 commit 和 MCP commit，避免两个独立仓库接口漂移。

## 13. 代码边界调整

### 13.1 前端

将 `frontend/app/page.tsx` 拆分为：

- `ConversationSidebar`
- `ConversationView`
- `MessageList`
- `MessageComposer`
- `useConversationList`
- `useConversationRun`
- `useAttachmentDraft`

页面组件只负责组合和顶层路由状态，SSE 解析继续保留在独立 API/transport 模块。

### 13.2 主后端

将 `api/router.py` 中的认证、对话、消息、运行查询和 SSE 拆为独立 router。
运行恢复、上下文构建和事件持久化分别进入独立 service，不得由 API handler 同时承担。

### 13.3 Diagnosis Repository

将当前 Repository 拆分为：

- schema/migrations
- device state and telemetry
- logs
- knowledge and cases
- diagnosis records
- outbox and external synchronization

拆分不改变公开 MCP 工具契约，并以现有测试加新增迁移测试保护行为。

## 14. 交付顺序

### 阶段 A：发布阻断项

1. 修正模型缓存模式和 CPU/GPU 部署档位。
2. 引入 RunDispatcher 和启动恢复扫描。
3. 增加冷启动与重启恢复测试。

### 阶段 B：数据正确性和容量

1. 建立正式迁移框架。
2. 新增 current state、telemetry 和 received time schema。
3. 修复设备元数据 upsert。
4. 上线保留策略、dry-run 和存量去重迁移。
5. 移除正常启动全量外部重放。

### 阶段 C：长对话与事件治理

1. ContextBuilder 和预算元数据。
2. 消息游标分页及前端加载更早消息。
3. 附件回收。
4. delta 批量提交和终态后压缩。

### 阶段 D：服务选择和运维能力

1. 能力路由及歧义错误。
2. liveness/readiness、结构化日志和指标。
3. 前端组件/E2E、仓库自包含 CI。
4. 完成模块拆分和文档更新。

阶段 B 的破坏性清理只能在迁移验证和备份完成后启用。各阶段可独立发布，但不得跳过其迁移和
回归门槛。

## 15. Definition of Done

- 第 4–12 节的所有验收用例自动化并通过。
- 全新环境和已有数据卷各完成一次 Compose smoke。
- 后端重启演练不存在永久 `QUEUED/RUNNING` 任务。
- 12 台模拟设备连续运行 7 天，数据库增长符合配置的保留和采样预算。
- 固件升级、名称更新和时钟漂移验收通过。
- 服务注册顺序变化不影响知识、案例和控制 API 路由。
- 500 条消息和多个大附件的对话仍能在预算内运行并分页显示。
- 旧版数据库快照全部能迁移到最新版本，重复迁移不改变结果。
- 容器探针使用正确的 liveness/readiness 端点。
- 主仓库和 MCP 仓库在干净环境中分别通过自己的完整 CI。
- README 包含开发、GPU、无 GPU、首次联网下载、离线缓存、迁移、备份、恢复和清理命令。

## 16. 基线验证记录

本规格制定时的基线结果：

- 后端：24 tests passed。
- MCP 核心测试：78 tests passed；使用 MCP 自身虚拟环境收集完整测试时因缺少跨仓库
  `agents/app` 依赖失败。
- 前端：lint、TypeScript 和生产构建通过；未发现组件或 E2E 测试。
- 当前 Diagnosis SQLite：约 194,911 条 `device_status`、41,591 条 `device_log`，
  文件约 47.9 MB，数据时间跨度约 4 天。
- 当前后端 SQLite：约 4,457 条 `run_events`。

这些数字只作为改进前基线，不作为固定产品容量上限。
