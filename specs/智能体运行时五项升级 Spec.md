# 智能体运行时五项升级 Spec

版本：v1.0  
状态：Accepted
更新时间：2026-09-24（Asia/Shanghai）

## 1. 背景

小yi 当前已经具备较完整的 IoT 智能运维闭环：

```text
用户请求
  → AgentRun
  → IoT Diagnosis MCP
  → IoT Control MCP
  → 低风险自动执行 / 高风险人工审批
  → 恢复验证
  → 自动沉淀已验证故障案例
```

现有基础能力包括：

- `AgentRun` 的 `queued → running → completed | failed` 状态机；
- `RunDispatcher` 的原子认领、FIFO 调度、优雅停止和启动恢复；
- MCP 工具目录、风险策略和静态授权；
- `diagnosis_id` 与修复动作的强关联；
- 高风险修复提案、乐观锁审批和恢复验证；
- 修复成功后通过 MQTT 事件自动沉淀已验证案例；
- RunEvent、SSE、结构化日志、Prometheus 指标和审计日志；
- 对话历史、附件和工具输出的基础预算与裁剪。

当前主要缺口不是“缺少更多工具”，而是以下五项 Harness 能力仍不完整：

1. 运维闭环主要依赖 system prompt 约束，宿主没有持久化的固定工作流状态。
2. 模型停止调用工具后，系统缺少基于结构化证据的完成条件检查。
3. 工具事件规范化、观测和收尾逻辑仍散落在运行主流程中。
4. 自动沉淀案例已经解决“写入”，但尚未形成案例复用反馈、可信度、适用范围和失效治理。
5. 上下文超限时以省略为主，缺少完整结果归档、可恢复引用和分层压缩。

本次升级借鉴通用 Agent Harness 的 Workflow、Goal Gate、Hooks、Memory 和 Context Compact 思想，但保持小yi的领域边界：模型负责诊断判断，宿主负责流程和安全，结构化证据负责完成验收。

## 2. Goals

本次改造完成以下五个目标。

### G1. 固定 IoT Workflow Runtime

新增持久化的 IoT 运维工作流控制器，将以下阶段从提示词约定升级为宿主可验证的状态：

```text
diagnose
  → select_action
  → remediate / wait_approval
  → verify
  → archive_case
```

工作流必须：

- 消费稳定的语义事件，不直接依赖 MCP 原始信封；
- 支持诊断型和修复型两种目标；
- 支持高风险审批交接；
- 保存阶段、证据、关联 ID 和失败原因；
- 在进程重启和页面刷新后可恢复；
- 不允许模型跳过强制前置条件；
- 不引入任意工作流 DSL 或用户提交的可执行代码。

### G2. 确定性 Completion Gate

Agent 没有继续调用工具只表示当前模型轮次结束，不直接代表业务目标完成。

在 `AgentRun` 写入终态前增加确定性完成门，根据结构化工作流状态返回：

```text
PASS_FINAL     最终目标已完成
PASS_HANDOFF   已安全交接给用户或异步领域流程
CONTINUE       尚缺可在当前 Run 内补齐的步骤
FAIL           无法安全继续或证据表明操作失败
```

Completion Gate 不新增独立 LLM 判断器，不以模型自然语言声明作为完成证据。

### G3. 轻量生命周期 Hooks

从 Agent 主执行函数中抽离非核心横切逻辑，提供少量、静态、类型化的生命周期扩展点：

```text
before_run
after_tool
after_gate
after_run
on_error
```

Hooks 主要用于：

- 语义事件转换；
- 观测指标；
- 日志和 trace 上下文；
- 非关键通知；
- 输出摘要和脱敏后的审计辅助信息。

权限、审批、工具授权、`diagnosis_id` 关联校验、状态迁移和 Completion Gate 必须保留为显式主流程或强制策略，不得依赖可选 Hook。

### G4. 可恢复的上下文压缩

将现有“超限后省略”升级为分层、可恢复的压缩管线：

```text
结构化字段保护
  → 大工具结果脱敏后完整归档
  → 上下文替换为摘要 + artifact 引用
  → 旧轮次结构化总结
  → prompt_too_long 单次补救
```

压缩必须始终保留：

- 当前用户请求；
- 用户明确约束；
- 当前工作流目标和阶段；
- 审批状态；
- `diagnosis_id`、`proposal_id`、`command_id`、`case_id`；
- Completion Gate 所需结构化证据。

## 3. Non-Goals

本次不包含：

- 通用 Task DAG、`blockedBy` 和多 Agent 任务认领；
- 多设备并行工作流；
- 定时任务、Cron Scheduler 或用户可配置计划任务；
- 通用后台命令执行平台；
- 动态插件市场或运行时加载第三方 Hook；
- 用户提交任意 Workflow DSL、Python、Shell 或表达式；
- 绕过 MCP 风险策略的自动操作；
- 高风险修复自动批准；
- 新增基础模型或训练、微调模型；
- 将完整对话永久作为 Memory；
- 自动删除或物理合并原始故障案例；
- Elasticsearch、图数据库或新的向量数据库；
- 替换现有 Dense + BM25 + RRF + Reranker 检索链路。

## 4. 设计原则与强制不变量

### 4.1 模型、宿主与证据的职责

```text
模型：理解问题、形成诊断、选择合适工具和动作
宿主：执行固定流程、权限控制、状态持久化、恢复和审计
证据：决定流程是否可以进入下一阶段或宣告完成
```

### 4.2 强制不变量

1. 没有有效 `diagnosis_id`，不得执行修复或创建修复提案。
2. `diagnosis_id` 指向的设备必须与目标设备一致。
3. 高风险动作必须进入 `waiting_approval`，不得由 Workflow 或 Hook 自动批准。
4. 没有 `verify_status=succeeded`，不得宣称修复成功。
5. 模型文本不是状态迁移证据；只有经过校验的工具结果、数据库记录和领域事件可以作为证据。
6. 自动沉淀案例必须来自明确关联、验证成功的修复事件。
7. Completion Gate 不得隐藏失败；业务失败允许生成诚实的最终答复，但不得伪装为恢复成功。
8. Hook 不得绕过工具权限、审批、关联校验或数据库事务。
9. 上下文压缩不得破坏 tool call / tool result 配对，不得丢失当前用户请求和安全约束。
10. 归档前必须先执行脱敏；Artifact 不保存 API Key、Authorization Header、Cookie 或 Session Token。
11. 新表和新字段必须通过版本化迁移创建，禁止运行时动态补丁。

## 5. Target Architecture

```text
                         User Message
                              │
                              ▼
                    Context Compact Pipeline
                              │
                              ▼
                     Agent Runtime / LLM
                              │
                        MCP tool calls
                              │
                              ▼
                  Mandatory Policy Boundary
               permission / correlation / approval
                              │
                              ▼
                   Tool Semantic Adapters
                              │
               ┌──────────────┴──────────────┐
               │                             │
               ▼                             ▼
        Lightweight Hooks             Workflow Runtime
     metrics / trace / audit aid       persisted state
                                             │
                                             ▼
                                      Completion Gate
                                  ┌──────────┼──────────┐
                                  │          │          │
                              CONTINUE    HANDOFF      FINAL
                                  │          │          │
                                  └──────► AgentRun ◄───┘

Recovery succeeded
       │
       ▼
Automatic verified case write
```

## 6. G1：Workflow Runtime 详细设计

### 6.1 工作流类型与激活

首版只注册一个受信任工作流：

```text
iot_remediation_v1
```

工作流不由用户上传，也不由模型生成。

激活规则：

- 普通聊天、知识问答不创建工作流；
- `diagnose_fault` 成功并返回有效 `diagnosis_id` 时创建或关联工作流；
- 工作流初始 `goal=diagnosis`；
- 一旦出现 `execute_device_action` 或 `create_remediation_proposal` 意图，目标单向升级为 `remediation`；
- 一个 `AgentRun` 首版最多关联一个设备和一个活动工作流；
- 同一 Run 尝试操作第二台设备时返回 `WORKFLOW_MULTI_DEVICE_UNSUPPORTED`，不得静默混合状态。

### 6.2 语义事件

新增静态 `ToolSemanticAdapter`，将已授权 MCP 工具结果转换为后端稳定事件：

| 语义事件 | 来源 | 最小载荷 |
| --- | --- | --- |
| `diagnosis.completed` | `diagnose_fault` 成功 | device_id, diagnosis_id, fault_type, confidence |
| `remediation.action_selected` | 执行动作或提案调用前 | device_id, action, risk_level, diagnosis_id |
| `remediation.command_started` | `execute_device_action` 成功 | command_id, device_id, action, diagnosis_id |
| `remediation.proposal_created` | `create_remediation_proposal` 成功 | proposal_id, device_id, action, diagnosis_id, status |
| `remediation.verification_updated` | `get_action_result` | command_id, command_status, verify_status, case_status |
| `remediation.proposal_decided` | 审批 REST 端点 | proposal_id, decision, command_id, decided_by |
| `case.archive_updated` | Control 返回或查询结果 | command_id, case_status, case_id, case_error |

适配器必须校验 MCP `ok`、字段类型、ID 格式和设备关联。无效结果仍保存原始 `tool.finished` 摘要，但不得推动工作流状态。

前端和 Workflow Runtime 只依赖语义事件，不解析 MCP 原始信封。

### 6.3 工作流状态

`OperationWorkflow.status`：

```text
active
waiting_approval
waiting_verification
completed
failed
cancelled
```

`OperationWorkflow.outcome`：

```text
diagnosed
awaiting_approval
remediated_verified
remediated_verified_archive_pending
remediation_failed
cancelled
```

`WorkflowStep.status`：

```text
pending
running
waiting
completed
skipped
failed
```

固定步骤：

| step_key | 说明 | 可跳过条件 |
| --- | --- | --- |
| `diagnose` | 产生有效诊断 | 不可跳过 |
| `select_action` | 明确动作及风险 | goal=diagnosis |
| `approve` | 用户批准高风险提案 | goal=diagnosis 或低风险动作 |
| `remediate` | 执行设备动作 | goal=diagnosis；拒绝提案时记 skipped |
| `verify` | 验证设备恢复 | goal=diagnosis；动作未执行时记 skipped |
| `archive_case` | 关联自动沉淀案例 | goal=diagnosis；修复未成功时记 skipped |

### 6.4 状态转换

诊断型：

```text
diagnosis.completed
  → diagnose.completed
  → 其余步骤 skipped
  → workflow.completed(outcome=diagnosed)
```

低风险修复：

```text
diagnosis.completed
  → action_selected
  → command_started
  → waiting_verification
  → verification_updated(succeeded)
  → archive_case archived | waiting
  → completed(remediated_verified | remediated_verified_archive_pending)
```

高风险修复：

```text
diagnosis.completed
  → proposal_created
  → waiting_approval
  → AgentRun 可 PASS_HANDOFF
  → 用户 approve
  → command_started
  → waiting_verification
  → verification_updated
  → archive_case
```

用户拒绝：

```text
proposal_decided(rejected)
  → approve.completed(decision=rejected)
  → remediate/verify/archive_case skipped
  → workflow.cancelled(outcome=cancelled)
```

修复或验证失败：

```text
command failed | verify_status=failed
  → 当前 step failed
  → workflow.failed(outcome=remediation_failed)
```

### 6.5 数据模型

后端新增迁移 `0004_operation_workflows.py`。

#### `operation_workflows`

```text
id                    UUID PK
agent_run_id          FK agent_runs.id, indexed
conversation_id       FK conversations.id, indexed
user_id               FK users.id, indexed
workflow_type         string, default iot_remediation_v1
workflow_version      integer, default 1
goal                  diagnosis | remediation
status                active | waiting_approval | waiting_verification | completed | failed | cancelled
outcome               nullable string
current_step          string
device_id             nullable string, indexed
diagnosis_id          nullable string, indexed
proposal_id           nullable string, indexed
command_id            nullable string, indexed
case_id               nullable string, indexed
state_json            JSON
lock_version          integer, default 1
created_at            datetime
updated_at            datetime
finished_at           nullable datetime
```

约束：

- `agent_run_id` 唯一；
- 所有关联 ID 一旦设置，不允许被不同值覆盖；
- 更新使用 `lock_version` 乐观锁；
- `completed | failed | cancelled` 为终态，不允许回退；
- 审批后的后续状态可以由原工作流继续更新，不创建第二个工作流。

#### `operation_workflow_steps`

```text
id                    UUID PK
workflow_id           FK operation_workflows.id
step_key              string
sequence              integer
status                pending | running | waiting | completed | skipped | failed
attempt_count         integer
input_json            JSON
evidence_json         JSON
error_code            nullable string
error_message         nullable string
started_at            nullable datetime
finished_at           nullable datetime
updated_at            datetime
```

唯一约束：`(workflow_id, step_key)`。

`evidence_json` 只保存完成门需要的结构化字段和 Artifact 引用，不复制整个工具输出。

### 6.6 恢复与幂等

- 语义事件必须携带稳定 `event_key`；建议为 `run_id:event_type:call_id`，审批事件使用 `proposal_id:version:decision`。
- 新增 `operation_workflow_events` 或在现有 `RunEvent` 中保存唯一 `event_key`；同一事件重复到达不得重复推进步骤。
- 服务启动时不自动重放已终态工作流。
- `active` 且所属 AgentRun 为 `RUNNING` 的工作流随现有 Run 恢复策略处理。
- `waiting_approval` 和 `waiting_verification` 不因后端重启标记失败。
- 审批 API、提案详情 API 和运行详情 API读取 Control 状态后，必须通过同一语义适配器幂等同步工作流。
- 本 Spec 不新增通用定时轮询；Control MCP 继续负责命令超时、验证窗口和案例归档事件重试。

### 6.7 API 与前端

新增：

```text
GET /api/v1/agent-runs/{run_id}/workflow
GET /api/v1/operation-workflows/{workflow_id}
```

返回工作流摘要、步骤、关联 ID、当前状态和最近错误；不返回原始敏感工具输出。

SSE 新增：

```text
workflow.started
workflow.step_updated
workflow.waiting_approval
workflow.waiting_verification
workflow.completed
workflow.failed
```

前端运行记录展示固定阶段进度。审批卡仍是唯一审批入口，不新增自动批准入口。

## 7. G2：Completion Gate 详细设计

### 7.1 Gate 输入

`CompletionGate.evaluate()` 只读取：

- `OperationWorkflow` 与步骤状态；
- 已规范化的语义事件；
- Control 返回的结构化命令、验证和案例状态；
- 当前 Run 剩余 continuation 次数；
- 工具能力是否可用；
- 用户是否需要进一步操作。

不得使用以下内容作为单独通过依据：

- assistant 自然语言中的“已完成”“已恢复”；
- 未经适配器校验的 MCP 原始字符串；
- 仅有 `command_status=succeeded`、但没有 `verify_status=succeeded` 的命令；
- 仅有相似案例、但没有本次设备证据的推断。

### 7.2 Gate 结果

```python
CompletionDecision(
    action="pass_final|pass_handoff|continue|fail",
    reason_code="...",
    message="...",
    required_action={...} | None,
    evidence={...},
)
```

### 7.3 判定表

| 场景 | Gate 结果 |
| --- | --- |
| 非 IoT 工作流 | `PASS_FINAL` |
| 诊断型目标且 diagnose completed | `PASS_FINAL` |
| 高风险提案已持久化且 pending | `PASS_HANDOFF` |
| 命令仍 running，且可在当前 Run 查询 | `CONTINUE` |
| 命令 succeeded 但缺恢复验证 | `CONTINUE` |
| 恢复验证 succeeded，案例 archived | `PASS_FINAL` |
| 恢复验证 succeeded，案例归档 pending | `PASS_FINAL`，outcome 标记 archive_pending |
| 提案 rejected / expired | `PASS_HANDOFF`，必须明确未执行 |
| 修复或验证 failed | `PASS_FINAL`，业务结果必须明确失败，不得描述为恢复成功 |
| 关联冲突、权限绕过或状态损坏 | `FAIL` |
| 需要的 MCP 能力不可用 | `FAIL` 或诚实降级为 `PASS_HANDOFF`，由稳定错误码决定 |

业务失败与系统失败必须区分：设备修复失败但 Agent 已正确解释结果时，`AgentRun` 可以 `completed`，工作流为 `failed/remediation_failed`；运行时异常、状态损坏或安全校验失败才将 `AgentRun` 标记为 `failed`。

### 7.4 有界续轮

- 默认 `completion_gate_max_continuations=2`；
- `CONTINUE` 时，宿主追加结构化 continuation 指令，明确缺失证据和允许调用的下一步工具；
- continuation 进入新的模型调用，但仍属于同一 `AgentRun` 和同一工作流；
- continuation 输入必须包含工作流快照，不依赖模型回忆旧文本；
- 达到上限后不得循环，转为 `PASS_HANDOFF` 或 `FAIL`；
- 每次 Gate 结果写入 `RunEvent` 和 `runtime_state.completion_gate`。

### 7.5 稳定 reason codes

至少包含：

```text
GOAL_DIAGNOSIS_COMPLETE
GOAL_REMEDIATION_VERIFIED
WAITING_USER_APPROVAL
WAITING_DEVICE_VERIFICATION
CASE_ARCHIVE_PENDING
REMEDIATION_FAILED
PROPOSAL_REJECTED
PROPOSAL_EXPIRED
REQUIRED_EVIDENCE_MISSING
WORKFLOW_STATE_CONFLICT
WORKFLOW_CAPABILITY_UNAVAILABLE
COMPLETION_GATE_LIMIT_REACHED
```

## 8. G3：轻量生命周期 Hooks 详细设计

### 8.1 边界

新增内部模块 `backend/app/agent/lifecycle.py`。首版只允许代码内静态注册，不提供数据库配置、第三方入口或动态导入。

Hook context 为只读快照：

```text
run_id
workflow_id
user_id
conversation_id
request_id
event_type
tool_name
server_name
call_id
sanitized_input_summary
sanitized_output_summary
timestamps
```

Hook 不接收 API Key、Authorization Header、Cookie、完整附件正文或未脱敏大输出。

### 8.2 扩展点

| Hook | 时机 | 允许用途 |
| --- | --- | --- |
| `before_run` | Context 构建后、Runtime 启动前 | trace、指标标签、工作流上下文记录 |
| `after_tool` | 工具结果经策略校验和脱敏后 | 语义事件旁路观测、指标、审计辅助 |
| `after_gate` | Gate 已完成确定性判断后 | Gate 指标、诊断日志 |
| `after_run` | Run 终态事务提交后 | 非关键通知、统计 |
| `on_error` | 运行异常已经分类后 | 结构化错误观测 |

以下不是 Hook：

- MCP 工具授权；
- 风险策略判断；
- 高风险审批；
- `diagnosis_id` 关联校验；
- 工作流状态迁移；
- Completion Gate 本身；
- AgentRun 终态提交。

这些逻辑必须由主流程显式调用并有独立单元测试。

### 8.3 执行语义

- 注册顺序固定并可测试；
- 同一扩展点默认串行执行，避免不可预测的提交顺序；
- Hook 默认不得修改传入对象；
- Hook 返回 `HookObservation`，不能直接返回控制流指令；
- 单个观测 Hook 异常只记录 `hook.failed`，不得重复执行设备动作；
- `after_run` Hook 失败不得回滚已经提交的 Run 终态；
- 强一致审计必须与业务写入处于同一显式事务，不得依赖 Hook；
- Hook 必须有超时；默认 500ms，可按 Hook 缩短，不允许无限等待；
- Hook 不得递归触发 Agent 或 MCP 工具。

### 8.4 与语义适配器关系

语义适配器是强制执行组件，先于 `after_tool` Hook：

```text
tool result
  → mandatory validation
  → sanitization
  → semantic adapter
  → workflow transition transaction
  → after_tool hooks
```

因此 Hook 失败不会造成工具已执行但工作流状态未更新。

## 9. G4：可恢复上下文压缩详细设计

### 10.1 当前链路的升级边界

现有 `ContextBuilder` 已按 token 预算保留当前消息、优先省略旧附件并按完整语义轮次裁剪；`RunEventBuffer` 已对大工具输出保存摘要、原始字节数和 SHA-256。

本次在此基础上增加“完整脱敏结果可恢复”，不取消现有预算和事件保留策略。

### 10.2 四层压缩

#### L0：关键结构保护

任何裁剪前先提取并保护：

```text
ok / error.code
device_id
diagnosis_id
proposal_id
command_id
case_id
command_status
verify_status
case_status
risk_level
workflow current_step/status/outcome
```

这些字段进入工作流 evidence，不依赖大输出正文。

#### L1：大结果归档

超过 `run_tool_output_inline_bytes` 的脱敏工具输出：

1. 序列化为 UTF-8 JSON 或 text；
2. 执行 secret sanitizer；
3. 写入 Artifact Store；
4. 计算 SHA-256 和字节数；
5. RunEvent 和模型上下文保留结构化摘要、前缀预览和 `artifact_id`。

不得先截断再归档。

#### L2：模型调用前压缩

使用 OpenAI Agents SDK `RunConfig.call_model_input_filter` 在每次模型调用前处理输入：

- 保留尚未被模型消费的最新工具结果；
- 保留最近 N 条已消费工具结果；
- 更早的大结果替换为 Artifact 引用和关键字段；
- 保护 tool call / tool result 配对；
- 注入当前 Workflow Snapshot；
- 达到目标预算后停止，不调用额外模型。

#### L3：历史总结

在 L0-L2 后仍超预算时生成结构化 `ConversationContextSnapshot`：

```text
current_goal
confirmed_facts
decisions
user_constraints
workflow_state
open_items
important_ids
covers_through_message_id
source_transcript_artifact_id
```

摘要被明确标记为背景信息，不是新的用户指令。当前用户消息始终单独保留。

模型摘要失败或未配置模型时，使用确定性 fallback：保留最近完整轮次、工作流快照和关键 ID，省略更早普通文本。

#### L4：API 超限补救

若字符/token 估算后仍收到 `prompt_too_long`：

- 完整脱敏输入归档为 transcript artifact；
- 再执行一次更激进压缩；
- 最多重试一次；
- 再次失败返回稳定错误 `CONTEXT_COMPACTION_EXHAUSTED`；
- 不得无限重试。

### 10.3 Artifact Store

后端新增迁移 `0005_run_artifacts_and_context_snapshots.py`。

#### `run_artifacts`

```text
id                    UUID PK
run_id                FK agent_runs.id, indexed
kind                  tool_output | transcript | context_snapshot_source
storage_uri           string
content_type          string
size_bytes            integer
sha256                string
redaction_version     string
created_at            datetime
expires_at            nullable datetime
```

首版提供 `LocalArtifactStore`，写入独立持久化目录；接口必须允许未来替换对象存储。数据库只保存元数据和 URI，不把任意大正文塞入 `RunEvent`。

Artifact 文件路径由服务端生成，禁止使用用户输入拼接；必须验证最终路径位于配置根目录内。

#### `conversation_context_snapshots`

```text
id                        UUID PK
conversation_id           FK conversations.id, indexed
covers_through_message_id FK messages.id
summary_json              JSON
source_artifact_id        FK run_artifacts.id
estimated_tokens          integer
created_at                datetime
```

同一 `covers_through_message_id` 只保留一个活动快照。新快照覆盖范围必须单调向前。

### 10.4 Artifact 读取边界

- Artifact 默认仅供后端重新构建上下文和管理员排障；
- 不新增浏览器直接文件路径；
- 普通用户 API 不返回 `storage_uri`；
- 下载/查看功能如后续需要，必须单独增加授权 API 和审计，本轮不做；
- 保留期遵循 RunEvent 诊断期，失败 Run 可以保留更久；
- Artifact 删除只删除可重建/已过期数据，必须纳入现有 retention dry-run 和指标。

### 10.5 与 RunEventBuffer 的兼容

`tool.finished` 超限后的事件结构升级为：

```json
{
  "output": {
    "truncated": true,
    "artifact_id": "...",
    "original_bytes": 123456,
    "sha256": "...",
    "summary": "...",
    "critical_fields": {
      "command_id": "...",
      "verify_status": "succeeded"
    }
  }
}
```

现有消费者忽略新增字段后仍能工作。

## 10. 配置

新增建议配置：

```text
WORKFLOW_RUNTIME_ENABLED=true
WORKFLOW_VERSION=1
COMPLETION_GATE_ENABLED=true
COMPLETION_GATE_MAX_CONTINUATIONS=2
HOOK_TIMEOUT_MS=500

RUN_TOOL_OUTPUT_INLINE_BYTES=65536
RUN_ARTIFACT_ROOT=./data/run-artifacts
RUN_ARTIFACT_RETENTION_HOURS=168
CONTEXT_KEEP_RECENT_TOOL_RESULTS=3
CONTEXT_COMPACTION_TARGET_RATIO=0.8
CONTEXT_REACTIVE_COMPACTION_RETRIES=1
```

生产环境要求 `RUN_ARTIFACT_ROOT` 位于持久化卷，不得使用临时容器文件系统。

## 11. 可观测性

新增结构化事件：

```text
workflow_started
workflow_transition
workflow_conflict
completion_gate_decision
completion_gate_continuation
hook_failed
context_artifact_written
context_compacted
context_reactive_compaction
```

新增指标：

```text
xiaoyi_workflows_total{status,outcome}
xiaoyi_workflow_step_duration_seconds{step}
xiaoyi_completion_gate_decisions_total{action,reason_code}
xiaoyi_completion_gate_continuations_total
xiaoyi_hook_failures_total{hook,event}
xiaoyi_context_compactions_total{layer}
xiaoyi_context_artifact_bytes_total{kind}
xiaoyi_context_reactive_failures_total
```

日志不得包含密钥、Cookie、完整附件和未脱敏工具原文。

## 12. 安全要求

1. Workflow 不新增工具权限，只能消费当前用户已经获准的 MCP 工具。
2. 工作流状态不能将 `proposal_only` 升级成可执行权限。
3. 高风险动作始终通过现有审批 REST + CSRF + admin 门禁。
4. Workflow ID、Run ID、Proposal ID 的 API 查询必须执行所有权校验。
5. 语义适配器对所有外部字段做 schema 校验，字符串中的指令不参与状态迁移。
6. Hook context 默认最小化，禁止携带认证凭据。
7. Artifact 持久化前执行脱敏，写入后使用 SHA-256 校验完整性。
8. Artifact 路径不得由 MCP、模型或用户直接指定。
9. Context Snapshot 被视为不可信背景数据，不得覆盖当前用户请求或 system policy。
10. 案例删除必须保留现有审批与审计边界。

## 13. 迁移与兼容

### 14.1 后端

依次新增：

```text
0004_operation_workflows.py
0005_run_artifacts_and_context_snapshots.py
```

- 存量 AgentRun 不回填工作流；查询返回 `workflow=null`；
- 新功能通过 `WORKFLOW_RUNTIME_ENABLED` 灰度；
- 关闭 Workflow 时恢复当前 AgentRun 行为；
- 新 RunEvent 类型对旧前端保持向后兼容；
- 不修改现有 `RunStatus` 枚举。

## 14. 实施阶段

### Phase 1：语义事件与轻量 Hooks

- 建立 ToolSemanticAdapter；
- 建立 lifecycle 模块；
- 保持现有 UI 行为；
- 用契约测试锁定语义事件。

### Phase 2：Workflow Runtime

- 新增工作流和步骤表；
- 消费语义事件并持久化转换；
- 接入审批 REST 和运行详情；
- 前端展示阶段状态。

### Phase 3：Completion Gate

- 在写 assistant message 和 `run.completed` 前执行 Gate；
- 增加有界 continuation；
- 覆盖 diagnosis、低风险、高风险、拒绝和失败路径。

### Phase 4：可恢复上下文压缩

- Artifact Store 和脱敏；
- RunEventBuffer 先归档后摘要；
- `call_model_input_filter` 分层压缩；
- ConversationContextSnapshot；
- retention 和指标。

每个 Phase 必须独立可发布、可关闭；不得要求五项全部完成后系统才能运行。

## 15. 测试计划

### 16.1 后端单元测试

- 每个语义适配器的成功、错误和字段缺失；
- 工作流全部合法转换和非法回退；
- 乐观锁冲突和重复事件幂等；
- Completion Gate 判定表；
- continuation 上限；
- Hook 顺序、超时和失败隔离；
- Artifact 路径、防穿越、脱敏和哈希；
- tool call/result 配对保护；
- Context Snapshot 覆盖范围单调性。

### 16.2 MCP 单元测试

- 自动沉淀仍直接生成 verified 案例；
- SQLite/MySQL/Qdrant 同步和 outbox 恢复。

### 16.3 集成测试

1. 仅诊断请求完成为 `diagnosed`。
2. 低风险动作执行、验证、案例归档完成。
3. 高风险动作进入等待审批，AgentRun `PASS_HANDOFF`。
4. 批准后沿原工作流继续更新，不创建重复工作流。
5. 拒绝和过期不会执行设备命令。
6. 设备命令成功但验证失败时不得宣称恢复。
7. 案例归档延迟时允许准确报告 archive pending。
8. 重放相同 remediation 事件不重复写案例或反馈。
9. 后端重启后 waiting 状态仍可查询和推进。
10. 大工具输出归档后，Agent 仍能使用关键字段完成 Gate。

### 16.4 前端 E2E

- 工作流步骤随 SSE 更新；
- 刷新页面后恢复阶段状态；
- 审批卡与工作流状态一致；
- 失败、等待和完成使用不同文案；
- 普通用户看不到 Artifact 路径和敏感信息。

## 16. Acceptance Criteria

### Workflow Runtime

- **AC1**：`diagnose_fault` 成功后创建唯一工作流，重复事件不重复创建。
- **AC2**：首版一个工作流只能绑定一个设备，设备冲突被稳定错误拒绝。
- **AC3**：所有状态迁移由经过校验的语义事件驱动，模型文本不能推进状态。
- **AC4**：低风险、高风险、拒绝、过期、验证失败路径均符合状态表。
- **AC5**：`waiting_approval` 和 `waiting_verification` 在后端重启后保持可恢复。
- **AC6**：审批后复用原工作流，关联 proposal/command/case ID 不可被不同值覆盖。
- **AC7**：工作流 API 执行用户所有权校验，前端刷新后可恢复步骤展示。

### Completion Gate

- **AC8**：没有 `verify_status=succeeded` 时，最终答复不得描述修复成功。
- **AC9**：pending 高风险提案返回 `PASS_HANDOFF`，不占用运行线程等待人工审批。
- **AC10**：修复业务失败可以诚实完成对话，但工作流 outcome 必须为 `remediation_failed`。
- **AC11**：状态冲突和安全关联错误使 AgentRun 失败并返回稳定错误码。
- **AC12**：`CONTINUE` 最多执行配置次数，达到上限后不会无限循环。
- **AC13**：每次 Gate 决策都有 RunEvent、reason_code 和 evidence 摘要。

### Hooks

- **AC14**：Hook 静态注册、执行顺序确定且有契约测试。
- **AC15**：任一观测 Hook 失败不会重复执行工具或回滚已提交终态。
- **AC16**：权限、审批、关联校验、状态迁移和 Gate 均不依赖可选 Hook。
- **AC17**：Hook context 不包含密钥、Cookie、完整附件和未脱敏大输出。

### Context Compact

- **AC18**：大工具结果先脱敏完整归档，再在 RunEvent 和模型输入中摘要。
- **AC19**：摘要包含 artifact_id、原始字节数、SHA-256 和关键结构字段。
- **AC20**：压缩不破坏 tool call/result 配对，不丢失当前用户请求和 Workflow Snapshot。
- **AC21**：`diagnosis_id`、`proposal_id`、`command_id`、`case_id` 在任何压缩层级后仍可用于 Gate。
- **AC22**：prompt too long 最多补救一次，再失败返回 `CONTEXT_COMPACTION_EXHAUSTED`。
- **AC23**：Artifact 路径不可穿越配置根目录，普通 API 不泄露 storage URI。
- **AC24**：Artifact 纳入 retention dry-run、执行开关、删除指标和失败诊断期。

### 全量门槛

- **AC25**：后端 Ruff、format、mypy、pytest 全部通过。
- **AC26**：MCP Ruff、format、mypy、pytest 全部通过。
- **AC27**：前端 lint、format、typecheck、组件测试、E2E 和 production build 全部通过。
- **AC28**：Docker Compose Portable 档位完成诊断、低风险修复、高风险审批、恢复验证和上下文大输出 smoke。
- **AC29**：升级和回滚演练均不丢失现有对话、Run、提案、命令和故障案例。

## 17. Rollback

- `WORKFLOW_RUNTIME_ENABLED=false`：新请求恢复当前 AgentRun 行为；已存在工作流保留只读查询。
- `COMPLETION_GATE_ENABLED=false`：仅用于紧急回滚，生产关闭必须产生告警。
- Hooks 可逐个静态禁用，但强制策略不可禁用。
- Context Compact 可回退到当前 ContextBuilder 和 RunEvent 摘要；Artifact 只读保留直至 retention 清理。
- 回滚不得降级数据库 schema 或删除新增列，代码必须保持向后读取兼容。

## 18. 主要改动位置

后端预计涉及：

```text
backend/app/models.py
backend/app/agent/runtime.py
backend/app/agent/lifecycle.py                  # new
backend/app/agent/tool_semantics.py             # new
backend/app/services/runs.py
backend/app/services/workflows.py               # new
backend/app/services/completion_gate.py          # new
backend/app/services/context_builder.py
backend/app/services/context_compactor.py        # new
backend/app/services/artifacts.py                # new
backend/app/services/run_event_buffer.py
backend/app/api/runs.py
backend/app/api/remediation.py
backend/migrations/versions/0004_operation_workflows.py
backend/migrations/versions/0005_run_artifacts_and_context_snapshots.py
```

Diagnosis MCP 预计涉及：

```text
mcp-services/iot_diagnosis/mysql_migrations/
mcp-services/iot_diagnosis/remediation.py
mcp-services/iot_diagnosis/diagnosis.py
mcp-services/iot_diagnosis/repositories/knowledge_cases.py
mcp-services/iot_diagnosis/retrieval/hybrid.py
mcp-services/iot_diagnosis/retrieval/fusion.py
mcp-services/iot_diagnosis/external.py
mcp-services/iot_diagnosis/rebuild.py
mcp-services/iot_diagnosis/server.py
```

前端预计涉及：

```text
frontend/components/conversation-view.tsx
frontend/components/remediation-card.tsx
frontend/components/run-records-sheet.tsx
frontend/components/knowledge-dialog.tsx 或独立 case dialog
frontend/lib/api.ts
frontend/hooks/use-conversation-run.ts
```

## 19. 最终交付定义

本 Spec 完成后，小yi应形成以下稳定闭环：

```text
模型提出诊断和动作
  → 强制策略校验权限与关联
  → Workflow Runtime 保存业务阶段
  → Completion Gate 用结构化证据决定结束、继续或交接
  → 恢复成功自动沉淀 verified 案例
  → 长对话和大工具结果通过可恢复压缩持续运行
```

最终目标不是把小yi改造成通用 Agent 平台，而是让现有 IoT 运维 Agent 在长流程、审批、恢复、经验复用和上下文增长场景下更加确定、可恢复、可审计。

## 20. 验收记录（2026-09-24）

| 验收项 | 结果与证据 |
| --- | --- |
| AC1–AC7 Workflow Runtime | 语义事件、单设备约束、幂等、审批复用、重启恢复、所有权和前端刷新由后端工作流测试、前端 E2E 与 2026-09-23 在线烟测覆盖。 |
| AC8–AC13 Completion Gate | 判定表、稳定 reason code、有界续轮、失败与交接路径由后端测试覆盖；在线 RunEvent 已核对 Gate 决策与证据摘要。 |
| AC14–AC17 Hooks | 静态注册、顺序、超时、失败隔离和脱敏边界由后端契约测试覆盖；强制策略仍在主流程。 |
| AC18–AC24 Context Compact | Artifact 脱敏、路径、哈希、关键字段、配对保护、快照单调性、超长提示补救和 retention 由后端测试覆盖；2026-09-23 在线大输出烟测验证 10 个归档文件的字节数与 SHA-256。 |
| AC25 后端门槛 | Ruff check/format、mypy 通过；追加历史命令只读回归后 pytest 通过。 |
| AC26 MCP 门槛 | Ruff check/format、mypy 通过；pytest 通过。 |
| AC27 前端门槛 | lint、format、typecheck、组件测试、1 项 Playwright E2E 与 production build 通过。组件测试覆盖 Run 失败与连接失败的文案区分。 |
| AC28 Compose 烟测 | 2026-09-23 在 Portable 档位用真实 API/模型完成诊断、低风险与高风险修复、审批、验证和大输出归档；2026-09-24 复核 backend/Diagnosis/Control readiness 均正常。 |
| AC29 回滚演练 | 2026-09-23 关闭 Workflow 与 Gate 开关后，新请求回到旧行为，已有工作流只读可查；对话、Run、工作流和案例计数无损，恢复开关后行为正常。 |

收尾修复：后端测试去除跨测试模块导入，保证独立 pytest 收集；此前的七天十二节点耐久观察属于系统可靠性规格的独立时间型验收，不计入本 Spec 的 AC1–AC29。

验收后回归：用户查询历史命令时曾触发 `REQUIRED_EVIDENCE_MISSING`。现仅允许与本轮工作流已绑定的命令结果推进验证；2026-09-24 重建后端后，以真实 API 查询历史命令，`get_action_result` 成功且 Run completed，本轮工作流数量为 0。既有跨设备与关联 ID 冲突仍保持硬拒绝。
