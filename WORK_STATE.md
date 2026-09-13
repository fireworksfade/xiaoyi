# IoT Diagnosis 项目工作状态

更新时间：2026-09-12（Asia/Shanghai）

## 当前目标

v1.3 discovery 已实现并保持兼容；2026-09-12 完成一轮架构优化，同日新增 IoT Control MCP（v1.0 闭环运维 + v1.1 案例自动沉淀）：Agent 具备"诊断 → 决策 → 执行 → 验证 → 沉淀"的自主闭环能力（低风险直接执行、高风险提案审批），对话内闭环已落地并完成浏览器实测。同日将模拟节点从 2 台硬编码扩为 12 台机群（fleet.json 配置驱动）。

## 2026-09-13 知识库拆分（官方技术文档 + 真实案例库，案例可删除）

- 知识文档库对话框拆为两个标签页：「官方技术文档」（原按 source 分组的列表 + 上传/删除，原样迁入）与「真实案例库」（懒加载分页列表，含来源徽标：自动沉淀 / 人工确认 / 内置；可展开查看症状、根因、处置与验证人；支持内联确认删除，删除后同步清理 MySQL 镜像与 Qdrant 向量并展示 sync_status）。
- 官方技术文档真正入库：`ingest_recommended_documents.py` 新增 6 份映射（ESP-MQTT 官方指南、Mosquitto.conf 手册、WiFi 驱动指南、致命错误/复位原因/Watchdog 指南），容器内执行后知识库由 10 篇扩至 16 篇（新增 290 分块，MySQL 与 Qdrant 全部同步）；compose 为诊断服务补充 `knowledge` 只读挂载，使脚本可随源码重放。
- MCP 新增 `list_fault_cases`（read_only，分页）与 `delete_fault_case`（destructive），共 14 个工具；`_case_document` 向量 payload 补 `document_id` 字段（Qdrant 删除按其过滤），存量案例经 `rebuild_vector_index(["fault_cases"])` 一次性补齐；`external.py` 新增 MySQL `delete_fault_case` 镜像方法。
- 后端新增 `GET/DELETE /api/v1/fault-cases`（列表 CurrentUser；删除 Admin + CSRF + 审计 `fault_case.deleted`，要求删除工具为 approval_required），复用 knowledge.py 的 MCP 调用链；bootstrap 分级加入两个新工具。
- 前端 `lib/api.ts` 新增 `FaultCaseSummary`/`listFaultCases`/`deleteFaultCase`；React Compiler lint 收敛后 0 warning 0 error。
- 验证：MCP 73 passed（新增案例列表/删除与 payload 回归）；后端 24 passed（新增 5 个 /fault-cases 端点测试）；浏览器实测双标签呈现、案例删除全链路（11→10 条，sync_status=complete，语义检索不再命中已删案例，outbox 归零）。

## 2026-09-12 ESP32 模拟机群（12 节点）

- `iot_diagnosis/simulator.py` 重构为机群模拟器：新增 `--fleet <json>` 模式，单进程多线程、每台设备独立 MQTT 连接（client_id、遗嘱、命令订阅互不干扰），随机源以 device_id 派生种子保证机群行为跨重启可复现；单设备 CLI（`--device-id/--scenario/--interval`）保持向后兼容。
- 遥测拟真：设备画像含友好名称（自动注册写入设备表 `name`）、温度基线（冷库 4 °C、配电房 41 °C 等围绕基线 ±1 °C 抖动）、RSSI 基线（±4 dBm 抖动）、固件版本（1.1.4/1.2.0/1.3.1）与上报间隔（5–15 s）；健康设备每约 5 分钟发布一条运行日志，避免日志表膨胀。
- 新场景 `unstable`（温室 ESP32_10）：运行 120 s 保护期后每个周期以 1% 概率进入 60–120 s 离线片段（发 WARNING 日志 + offline status 后完全静默），片段结束自行恢复；`reconnect_wifi`/`restart_device` 命令可立即终结片段，闭环处置仍可用。
- `handle_command` 顺带修复：`update_firmware` 现在也会清除 unstable 离线片段（与 restart_device 语义一致）。
- 新增 `iot_diagnosis/fleet.json`（12 台：8 normal + mqtt_timeout/wifi_weak/sensor_error/unstable 各 1），加载校验 ID 唯一、场景合法、`temperature_base < 70`（防误报）。
- Compose：`iot-simulator` + `iot-simulator-wifi` 两服务合并为单个 `iot-simulator-fleet`（挂载 fleet.json，随源码热更新）。
- 优雅停机：main() 统一处理 SIGTERM/SIGINT，`docker compose stop` 时 12 台设备全部主动发布 `offline_reason=graceful_shutdown`（在线实测 12/12），强杀场景仍由遗嘱代发 `client_lost`。
- 测试：新增 `tests/test_simulator.py` 11 个用例（fleet 解析校验、画像遥测、故障场景、周期日志节奏、unstable 离线片段状态机、命令恢复）；`test_simulator + test_iot_control` 27 passed。
- 实机验收：compose 应用后旧模拟器容器移除，12 台设备自动注册且名称/基线/固件版本符合画像（ESP32_05 保留种子名"实验室节点 05"、ESP32_06 保留旧库默认名——`name` 仅首帧写入，需重置 diagnosis-data 卷才能刷新）。

## 2026-09-12 案例自动沉淀（IoT Control MCP v1.1）

- `execute_device_action` / `create_remediation_proposal` 新增可选 `diagnosis_id`，Agent 指令要求必传；提案批准后 diagnosis_id 传递到命令行。
- 恢复验证成功且关联诊断的命令进入归档队列；Control MCP 后台任务经高层 `mcp.client.Client`（Transport 适配器注入 Bearer 头）调用诊断 MCP `get_diagnosis_trace` 组装案例并经 `add_verified_fault_case` 写入案例库（`verified_by=auto-remediation:{command_id}`），`case_id` 回写命令；前端审批卡显示沉淀结果。
- 归档失败重试 5 次后放弃（case_error 记录原因）；诊断记录不存在直接跳过；device_command/remediation_proposal 表通过启动迁移补齐新列。
- MCP 56 passed（新增 9 个归档测试）；后端 18 passed；前端 lint/build 通过。
- 在线浏览器验收通过：Agent 运行中自动携带 diagnosis_id（CMD_20260912_5750D1A8 → 案例 F7C544AEF），审批卡显示"已自动沉淀为故障案例"；修复卡片轮询在任务完成后补拉一次以展示延迟回写的 case_id。
- 移除前端手动"验证案例"入口（CaseDialog 组件与 addVerifiedFaultCase API 封装已删）；后端 admin REST 端点与诊断 MCP 的 add_verified_fault_case 工具保留（自动沉淀与程序化修正仍需要）。
- 在线验证：`execute_device_action`（ESP32_05 reconnect_mqtt + diagnosis_id=DIA_20260911_D4CA41F8）→ 恢复验证 succeeded → 自动沉淀案例 `F067F37D2`（MySQL 已入库，`search_fault_cases` 语义检索命中排名第二）。注意：fork 的底层 ClientSession 不做 initialize 握手，服务间调用必须用高层 `Client`。

## 2026-09-12 自主运维闭环（IoT Control MCP v1.0）

- 新增独立服务 `mcp-services/iot_control/`（端口 9002），含 6 个工具：`list_device_actions`、`execute_device_action`（低风险白名单）、`create_remediation_proposal`（高风险提案）、`get_action_result`、`list_remediation_proposals`、`decide_remediation_proposal`（approval_required，仅后端 REST 直调，Agent 不可见）。
- 命令下发走 `iot/{device_id}/cmd`（QoS1），设备回执 `iot/{device_id}/cmd_ack`；SQLite 存 `device_command` 与 `remediation_proposal`（乐观锁 + 30 分钟过期）；applied 后进入验证窗口（默认 60s），窗口内有在线状态且无新 ERROR/fault 即判定恢复成功。
- 模拟器支持下行命令：reconnect_mqtt、reconnect_wifi、calibrate_sensor、set_reporting_interval、restart_device、update_firmware 均真实改变后续上报行为并发布恢复日志；compose 新增 ESP32_06（wifi_weak）模拟器。
- 后端：`bootstrap_local_mcp.py` 注册 `iot-control-local` 并分级授权（read_only / proposal_only / approval_required）；新增 `app/api/remediation.py`（提案列表、详情、决策端点，admin + CSRF + 审计日志 `remediation.approved/rejected`）；`process_agent_run` 把提案写入 assistant message metadata，刷新页面后审批卡可恢复；Agent 指令升级为闭环剧本，`max_turns` 8→14。
- 前端：新增 `components/remediation-card.tsx` 审批卡（批准/拒绝、任务状态轮询、恢复结果展示），实时流与历史消息均可渲染；`lib/api.ts` 新增提案类型与三个端点封装。
- Compose：新增 `iot-control-mcp`（9002，healthcheck /ready，control-data 卷），backend 的 MCP_ALLOWED_HOSTS 加入 iot-control-mcp。
- 验证：MCP 47 passed（含 11 个 control 新测试：白名单、状态机、乐观锁、过期、验证窗口、模拟器命令处理）；后端 18 passed（含 4 个决策端点测试：审批流、乐观锁/非 pending 冲突、admin+CSRF 门禁、控制服务发现）；前端 lint/build 通过。
- 规格：`specs/iot-control-mcp-spec-v1.0.md`。

## 2026-09-12 架构解耦（事件化归档 + 语义事件）

- Control MCP 不再通过 MCP 调用诊断服务：恢复验证收敛后向 `iot/{device_id}/remediation` 发布完成事件（`iot_control/remediation_events.py`），诊断服务订阅并自行沉淀案例（`iot_diagnosis/remediation.py`），经 `iot/{device_id}/remediation_case` 回发确认，Control 订阅确认把 case_id 关联回命令。`case_archive.py` 与服务间 MCP 客户端已删除，Control 对 Diagnosis 零感知。
- diagnosis_id 缺失时诊断服务按设备+时间窗兜底关联最近一次成功诊断（`latest_remediation_diagnosis`，窗口 `DIAGNOSIS_REMEDIATION_CORRELATION_MINUTES`）。
- 后端 `process_agent_run` 把提案工具结果翻译为语义事件 `remediation.proposal_created`（后端定义的干净载荷），前端改吃语义事件，不再匹配 MCP 工具名或解析 MCP 信封。
- MCP 61 passed（控制 17 + 诊断事件 8 + 既有回归）；后端 18 passed；前端 lint/build 通过；compose 移除 Control 的 DIAGNOSIS_MCP_URL/TOKEN 配置。

## 2026-09-12 架构优化

- Adaptive Router 新增语义路由：查询向量与各知识源原型向量按余弦相似度选择来源（约 10ms），`router=semantic`；LLM Router 降级为向量路由不可用时的兜底，省掉一次完整 LLM 往返。评测 router accuracy 1.0。
- 检索候选超过重排服务批量上限会静默降级的问题已修复：先按初筛分截取 Top 60 再重排，模型服务 `/rerank` 文档上限放宽到 200；此前因知识库扩到 311 分块触发 422 导致 fallback。
- 知识库删除闭环：新增 `delete_knowledge_document` MCP 工具（approval_required）+ 后端 `DELETE /knowledge-documents/{source}/{document_id}` + 前端两步确认删除；SQLite/MySQL/Qdrant 三处同步删除。
- MQTT 可靠性：MCP 订阅改为 QoS 1 + 持久会话（clean_session=False），mosquitto 开启持久化（`mqtt-data` 卷），模拟器增加遗嘱消息（进程崩溃时 Broker 代发离线状态）。
- outbox 多 worker 安全：`retry_external_sync` 改为单条 UPDATE 原子认领（`claimed_at` 租约 + 过期接管）。
- model_service embeddings 端点改为 async + micro-batching（5ms 窗口合并并发请求为一次 GPU encode）。
- 安全守卫：`APP_ENV=production` 时强制非默认 `APP_SECRET_KEY` 且 `SEED_DEMO_USERS=false`，否则启动失败。
- 前端：`page.tsx` 拆出 `KnowledgeDialog`（含删除）、`CaseDialog`、`RunRecordsSheet`（运行记录面板，新增 `GET /agent-runs` 列表端点）；知识库响应与审计日志透传 MCP `trace_id`。
- Compose 本地联调：MCP / retrieval-models 改为源码 bind-mount（不再依赖 Docker Hub 重建），MCP 容器加 `PYTHONPATH=/app`（修复 site-packages 旧包遮蔽挂载代码导致评测走旧行为的问题），retrieval-models 加 `HF_HUB_OFFLINE=1`（模型已本地缓存，避免启动联网探测卡 20+ 分钟）。
- 验证：MCP 36 passed（含工具 schema 契约测试：可空参数不得进入 required）；后端 14 passed；前端 lint/build 通过；live-retrieval 评测 router 1.0 / reranker 真实生效；浏览器实测运行记录面板与删除闭环通过；真实 LLM 诊断 `router=semantic`，总耗时 13.9s 中 LLM 本体 10.8s（提供方延迟为主）。

## 历史目标

v1.3 discovery 功能已实现；当前完成设备、诊断历史和知识文档的自发现能力，并保持此前工具兼容。

## 已完成

- 新版统一 MCP 位于 `mcp-services/iot_diagnosis/`，包含 12 个工具（保留 6 个 v1.0 工具并新增追踪、摄取、向量重建和三个发现工具）。
- 已移除旧 RAG / IoT MCP 相关代码、旧维修审批与执行接口及对应前端 UI。
- 新规范文件保留在 `specs/iot-diagnosis-mcp-spec-v1.0.md`。
- 已实现 MQTT `fault`、`heartbeat` 消息和设备离线检测。
- 已实现可配置的 LLM Router / Diagnosis 调用；未配置模型密钥时使用 `heuristic_fallback`。
- 已使用 `mimo-v2.5-pro` 完成真实 LLM Router / Diagnosis 在线验收；本地密钥仅保存在 Git 忽略的根 `.env` 中。
- 已实现人工确认故障案例的后端接口与前端弹窗。
- 已实现 MySQL 镜像写入和 Qdrant 向量索引：
  - 新文件：`mcp-services/iot_diagnosis/external.py`
  - MySQL 表：`device`、`device_status`、`device_log`、`knowledge_document`、`fault_case`、`diagnosis_record`
  - Qdrant 使用 384 维确定性特征向量，集合名由环境变量配置。
  - SQLite 仍为主存储；MySQL / Qdrant 当前采用双写与失败回退模式。
- `compose.yaml` 已加入：
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
- 已新增 v1.1 completion spec。
- 外部写入失败会进入 SQLite outbox，后台自动重试；案例写入不再误报向量索引成功。
- 启动快照的状态、日志、文档、案例与诊断回填失败也会逐项进入 outbox，避免外部存储启动较晚时漏数。
- MySQL / Qdrant 若在 MCP 启动时完全不可连接，重试循环会主动重建客户端，再继续幂等重放。
- 已新增 `get_diagnosis_trace`，成功和失败诊断均可按 ID 查询路由、上下文和观测数据。
- Rule Router 的实时查询现直接返回 `answer` 与完整 `realtime_state`，不再误走故障分析或调用 LLM。
- 诊断记录新增完整 `result_json` 快照，追踪结果可还原 severity、evidence、人工检查标记和实时回答等字段。
- 无模型回退已细分规格中的十类实验故障，不再把认证失败、Broker 不可达和网络延迟统一误判为 Keep Alive。
- 已新增 `ingest_knowledge_text` 及 TXT/Markdown/PDF 摄取 CLI，支持分块和同文档替换。
- Embedding 与 Reranker 已拆为可替换接口，支持离线 hash 和 OpenAI-compatible Embedding。
- Compose 已部署 GPU 模型服务：`Qwen3-Embedding-0.6B` 与 `Qwen3-Reranker-0.6B`，模型缓存持久化在 `retrieval-model-cache`。
- MCP 已切换到 1024 维 `iot_diagnosis_qwen3` 集合，7 条文档/案例均已使用真实语义模型重新生成向量；旧 384 维 `iot_diagnosis_knowledge` 集合已确认弃用并删除。
- 检索响应会报告 Embedding/Reranker provider 及 reranker fallback 状态。
- 已新增固定 JSONL 评测集及 RAG/Router/Diagnosis 指标脚本。
- 已新增可选 MCP Bearer Token、`/ready` 和 Compose healthcheck。
- 已完成 v1.2 core-model spec：Embedding provider、模型端点和 Qdrant 写入支持批处理。
- 已新增 `rebuild_vector_index`，可从 SQLite 批量重建全部或指定来源的知识分块与已确认案例。
- MCP `/ready` 已直接探测 Retrieval Models，返回 device、两个模型名和维度；模型不可用时报告 `retrieval_models` 并返回 503。
- 评测 CLI 已支持 `deterministic` 与 `live-retrieval` 两种 profile，并报告 provider、fallback、平均/P50/P95 延迟。
- 已新增 `list_devices`，可按设备类型和包含心跳新鲜度的有效在线状态过滤并分页。
- 已新增 `list_diagnoses`，可按设备、故障类型和成功/失败状态过滤诊断摘要并分页。
- 已新增 `list_knowledge_documents`，可按逻辑文档聚合分块并返回分块数、字符数和摄取时间。
- 主后端 bootstrap 会以只读策略自动启用三个发现工具。
- 已整理并摄取全部 10 份建议诊断资料，覆盖 ESP-MQTT 错误、MQTT Session/QoS、Mosquitto、WiFi 断线、致命错误与重启、Watchdog、Core Dump、内存泄漏/碎片、I2C 及 ADC；当前共 14 份逻辑文档、20 个知识分块。
- 可重复执行的 `scripts/ingest_recommended_documents.py` 已覆盖全部十份文档，原稿保存在 `mcp-services/knowledge/` 并打包进 MCP 镜像。
- 前后端联调发现并修复 Agent 运行失败：`mcp_config.convert_schemas_to_strict` 会把 MCP 工具可选参数强制必填，第三方 Chat Completions 模型对可空字段输出字符串 `"None"` 触发入参校验失败并耗尽 max turns；已改回原始 JSON Schema（`backend/app/agent/runtime.py`）。
- 已新增 `frontend/.env.local`（git 忽略）指向本地后端，前端 dev 服务器通过同源代理完成登录、会话 CRUD、SSE 与真实 LLM Agent 运行验证。

## 已通过的验证

- 后端测试：10 passed。
- MCP v1.3 回归：35 passed、1 skipped；Docker Streamable HTTP 在线发现及完整冒烟通过。
- 前端 lint 与 production build：通过。
- MCP 在线冒烟：8 个工具、实时直答、知识检索、诊断、完整追踪和人工确认门禁通过。
- 真实 LLM 在线冒烟返回 `route.router: llm`；最近诊断记录 LLM 延迟约 12.6 秒，输入 938 Tokens、输出 232 Tokens。
- 本地全栈冒烟：前端 200、同源代理、认证、会话 CRUD 和 SSE 通过。
- 浏览器级前后端联调：真实模型经 `list_devices`、`search_knowledge`、`search_fault_cases` 与 `diagnose_fault` 完成 ESP32_05 故障排查，诊断 `DIA_20260911_7CB937F6`（MQTT_CONNECTION，置信度 96.92%，约 12.2 秒）已入库可查；后端回归 10 passed。
- 经后端真实写入人工确认案例 `FC19D3B41`，返回 `mysql_saved: true`、`vector_indexed: true`。
- MySQL 已查到 `FC19D3B41`；Qdrant 集合状态为 `ok`，已查到对应向量点。
- 前端 lint 修复已验证并提交，仓库工作树干净。
- v1.1 本机 Bearer 验收：未授权请求返回 401，授权后发现并调用 8 个工具成功。
- 确定性评测：15 个用例；Recall@5、Hit Rate、Router Accuracy、Source Selection Accuracy、Diagnosis Accuracy、Diagnosis Name Accuracy 均为 1.0；本轮平均检索延迟约 2.94 ms。
- Qwen3 模型端点实测：Embedding 返回 1024 维向量，首次请求约 1.72 秒；Reranker 将 MQTT 相关文档以 0.9980 排名第一，首次请求约 1.45 秒。
- MCP 在线日志已确认实际调用 `/v1/embeddings` 和 `/rerank`；两模型常驻显存约 2.6GB。
- 在线 MCP 冒烟返回 `embedding_provider=openai_compatible`、`reranker.provider=qwen3_remote`、`reranker.fallback=false`。
- v1.2 在线 MCP 冒烟已发现并调用 9 个工具；完整诊断、追踪、实时直答和人工确认门禁通过。
- 批量 Embedding 实测一次输入两条文本，返回两组有序 1024 维向量。
- 全量向量重建实测 attempted=7、indexed=7、pending=0，耗时约 100.71 ms。
- 真实 Qwen3 检索评测：15 个用例，Recall@5/Hit Rate 均为 1.0，MRR 0.8013，平均 256.16 ms、P50 251.28 ms、P95 312.76 ms，reranker 未 fallback。
- v1.3 在线 MCP 冒烟已发现并调用 12 个工具；三个发现工具、真实 LLM 路由、诊断追踪、实时直答和人工确认门禁均通过。
- v1.3 镜像已在本地重新构建并由 Compose 启用；readiness 为 200，版本为 1.3.0，外部存储与 Qwen3 模型均 ready，outbox pending 为 0。
- 主后端目录已刷新为 12 个工具，三个新发现工具均按只读策略启用；后端回归 10 passed。
- 十类代表查询均将对应新文档排在第一位，Qwen3 reranker 未回退；当前 Qwen3 集合 23 个向量点，状态 green，outbox pending 为 0。
- 已定位前端真实模型未生效原因：管理员模型配置虽保存密钥但 `enabled=false`，且 Xiaomi Mimo 被设为 `responses`；现已改为启用并使用 `chat_completions`。端到端 Agent run 返回真实模型结果，约 5.8 秒完成，事件中无 Mock 的 `demo__inspect_request`。
- v1.1 Compose 在线冒烟：8 个工具、LLM Router、诊断追踪、实时直答和人工确认门禁均通过；实时直答约 1.8 ms，未调用 LLM。最新外部 LLM 完整诊断约 45.3 秒，功能正确但因提供方延迟未达到 8 秒目标。
- v1.1 真实恢复演练：停止 Qdrant 后写入返回 pending/outbox=1，恢复后自动同步到 Qdrant 并清零；演练案例已从 SQLite、MySQL、Qdrant 和 outbox 清理。
- v1.1 启动回填验收：MySQL 启动瞬时写入失败形成的 224 条 outbox 记录已由后台自动重放，最终 pending=0。
- 已生成并启用本地重建的 `xiaoyi-mcp-services 1.1.0` 镜像，在无源码挂载容器中通过 8 工具冒烟。

## 当前本地运行状态

Docker Compose 当前服务均已启动：backend、MCP、IoT Control MCP、Retrieval Models、MySQL、Qdrant 健康，MQTT 与两个模拟器（ESP32_05 mqtt_timeout / ESP32_06 wifi_weak）运行中。Docker Hub 已恢复，`iot-control-mcp` 与 `iot-simulator-wifi` 已用 `python:3.12-slim` 正式构建镜像并去掉 compose 中的镜像复用临时方案。已完成在线端到端验收：真实 LLM Agent 对 ESP32_05 自动诊断并执行 `reconnect_mqtt`（CMD_20260911_7FBBD3B2）后确认恢复；浏览器实测审批卡全流程通过（提案渲染 → 批准执行 → 执行中 → 恢复验证 succeeded，历史刷新后卡片恢复最新状态），期间修复了决策响应扁平结构解析崩溃与 `loadConversationList` 缺失提案映射两处前端缺陷。

## 当前待处理问题

- 当前 v1.3 发现能力的实现、镜像构建与在线验收已完成，没有已知阻塞问题。
- 外部 LLM 最近一次完整诊断约 45.3 秒；按当前优先级暂不进行性能与并发优化。
- Docker Hub 鉴权网络仍超时；已用本地基础镜像完成无缓存 v1.1 重建并切换 Compose。该问题只影响重新拉取全新的 `python:3.12-slim` 基础镜像，不影响当前产物和运行服务。

## 下一步

1. 端到端联调：`docker compose up -d --build` 拉起 iot-control-mcp 后重跑 `bootstrap_local_mcp.py`，前端实测对话内闭环（ESP32_05 MQTT 超时自动修复、ESP32_06 弱信号与 restart_device 审批卡）。
2. 如需进一步自治：新增后台故障监测，设备上报 fault 或离线时自动发起一次 Agent 运维运行（需处理 AgentRun 的 conversation FK 与系统会话）。
3. 主要功能之后如需继续，可优化外部 LLM 两阶段调用的端到端耗时。
4. Docker Hub 网络恢复后可执行 `docker compose build --no-cache iot-diagnosis-mcp iot-control-mcp`，重新拉取并验证全新基础镜像。
5. SerpAPI/联网检索属于 v1.1 明确排除项；如需加入，应另开扩展规格。
6. 为主仓库和 MCP 仓库分别配置远程地址并推送。

## 重要文件

- `compose.yaml`
- `mcp-services/.env.example`
- `mcp-services/pyproject.toml`
- `mcp-services/iot_control/server.py`
- `mcp-services/iot_control/repository.py`
- `mcp-services/iot_control/mqtt.py`
- `mcp-services/iot_control/actions.py`
- `mcp-services/iot_diagnosis/external.py`
- `mcp-services/iot_diagnosis/embeddings.py`
- `mcp-services/iot_diagnosis/ingestion.py`
- `mcp-services/iot_diagnosis/repository.py`
- `mcp-services/iot_diagnosis/reranker.py`
- `mcp-services/iot_diagnosis/retrieval.py`
- `mcp-services/iot_diagnosis/server.py`
- `mcp-services/iot_diagnosis/simulator.py`
- `backend/app/api/remediation.py`
- `backend/app/services/runs.py`
- `backend/scripts/bootstrap_local_mcp.py`
- `frontend/components/remediation-card.tsx`
- `specs/iot-diagnosis-mcp-spec-v1.0.md`
- `specs/iot-diagnosis-mcp-completion-spec-v1.1.md`
- `specs/iot-diagnosis-mcp-core-model-spec-v1.2.md`
- `specs/iot-diagnosis-mcp-discovery-spec-v1.3.md`
- `specs/iot-control-mcp-spec-v1.0.md`

## Git 状态

- 项目根目录已建立主 Git 仓库，默认分支为 `main`，跟踪 frontend、backend、deploy、specs、Compose 配置和项目文档。
- frontend 原有提交历史已完整导入主仓库，不再保留嵌套 `.git`。
- `mcp-services/` 是唯一的独立子目录仓库，默认分支为 `main`；首个提交为 `ac596d3 Initial IoT diagnosis MCP server`。
- MCP 仓库通过 `.gitignore` 排除了 SQLite 运行数据、本地 `.env`、Python/pytest 缓存和构建产物。
- 主仓库通过根 `.gitignore` 排除 `mcp-services/`、运行数据、虚拟环境、依赖目录和构建产物。
- v1.1 主仓库与 MCP 子仓库修改尚未提交。
- 最近相关提交：
  - `d7c73a0 Fix frontend lint compatibility`
  - `ad9542a Add verified fault case workflow`
  - `1513ddb Remove legacy repair approval UI`
  - `ff34a6a Proxy backend through same-origin site route`
- frontend 原仓库 bundle 与 `.git` 元数据备份位于 `D:\last-work-repo-backups\`。
