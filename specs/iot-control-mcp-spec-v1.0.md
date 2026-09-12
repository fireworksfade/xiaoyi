# IoT Control MCP Spec v1.0

状态：已实现（与 `mcp-services/iot_control/` 对应，v1.1 新增案例自动沉淀）
日期：2026-09-12
前置：IoT Diagnosis MCP v1.3（`specs/iot-diagnosis-mcp-discovery-spec-v1.3.md`）

## 1. 目标

让主 Agent 具备"诊断 → 决策 → 执行 → 验证"的闭环运维能力，而不是只给出诊断结论由人工操作。设备控制能力按诊断 spec v1.0 §40 的预留，独立为 IoT Control MCP，与诊断服务分开部署、分开授权。

## 2. 边界

- 本服务只负责：动作目录、命令下发（MQTT 下行）、命令回执、修复提案审批、恢复验证。
- 诊断能力仍在 IoT Diagnosis MCP；Control MCP 不复制设备状态与日志存储，仅在验证窗口内采样 MQTT 消息。
- 固件升级为模拟实现（版本号变更 + 等价重启）；真实升级不在范围内。

## 3. 设备下行通道

| 主题 | 方向 | QoS | 载荷 |
| --- | --- | --- | --- |
| `iot/{device_id}/cmd` | Control MCP → 设备 | 1 | `{command_id, action, parameters, reason, issued_by, issued_at}` |
| `iot/{device_id}/cmd_ack` | 设备 → Control MCP | 1 | `{command_id, status: applied\|failed, detail, timestamp}` |
| `iot/{device_id}/status`、`/logs`、`/fault` | 设备 → Control MCP | 1 | 仅在验证窗口内采样，用于恢复判定 |

模拟器（`iot_diagnosis/simulator.py`）订阅 `iot/{device_id}/cmd`，执行动作后发布回执与恢复日志，并真实改变后续上报内容（故障标志清除、uptime 归零、固件版本变更、上报间隔调整）。

## 4. 动作目录与分级自主

| 动作 | 风险 | 参数 | 适用故障 |
| --- | --- | --- | --- |
| reconnect_mqtt | low | — | MQTT 连接类 |
| reconnect_wifi | low | — | WiFi 弱信号/断线 |
| calibrate_sensor | low | — | 传感器读数异常 |
| set_reporting_interval | low | seconds (1–3600, 必填) | 上报/网络类 |
| restart_device | high | — | 运行时异常、兜底恢复 |
| update_firmware | high | version (必填) | 运行时异常 |

- 低风险动作：Agent 通过 `execute_device_action` 直接执行（后端策略 `proposal_only`）。
- 高风险动作：Agent 通过 `create_remediation_proposal` 创建提案，人工在聊天界面批准后由后端 REST 直调执行，Agent 永远无法直接执行高风险动作。

## 5. MCP 工具（6 个）

| 工具 | 注解 | 后端策略 | 说明 |
| --- | --- | --- | --- |
| `list_device_actions` | read_only | read_only | 动作目录（动作、风险、参数 schema、适用故障） |
| `execute_device_action` | readOnlyHint=false | proposal_only | 下发低风险动作；高风险返回 `ACTION_REQUIRES_APPROVAL` |
| `create_remediation_proposal` | readOnlyHint=false | proposal_only | 为高风险动作创建提案（默认 30 分钟过期） |
| `get_action_result` | read_only | read_only | 按 command_id 或 proposal_id 查询执行与验证状态 |
| `list_remediation_proposals` | read_only | read_only | 提案列表，可按状态过滤；过期待提案惰性标记 expired |
| `decide_remediation_proposal` | readOnlyHint=false | approval_required | 人工决策提案；批准后立即下发命令。仅后端 REST 直调，对 Agent 不可见 |

所有工具返回统一信封 `{ok, data, error, trace_id}`。`execute_device_action` 与 `create_remediation_proposal` 服务端校验动作存在性、风险级别与参数（`MISSING_PARAMETER` / `INVALID_PARAMETER` / `UNKNOWN_PARAMETER`）。

## 6. 状态机

命令：`pending → acked → applied | failed`；`applied` 后进入恢复验证窗口（默认 60s，`CONTROL_VERIFY_WINDOW_SECONDS`）；窗口内收到在线 status 且无新 ERROR/fault 日志 → `verify_status=succeeded`，否则 `failed`；`pending` 超过 30s（`CONTROL_COMMAND_TIMEOUT_SECONDS`）未回执 → `timeout`。

提案：`pending → approved | rejected | expired`（乐观锁 `version`，决策需携带 `expected_version`）；approved 后 `task_status` 跟随关联命令：`running → verifying → succeeded | failed`。

## 7. 存储

SQLite `CONTROL_DATABASE_PATH`（默认 `data/iot_control.db`）两张表：`device_command`、`remediation_proposal`。验证窗口采样保存在内存，最终结论写回命令与提案行。

## 8. 后端集成

- `bootstrap_local_mcp.py` 注册 `iot-control-local`（`http://iot-control-mcp:9002/mcp`），按第 5 节写入工具策略。
- `app/api/remediation.py`：`GET /api/v1/remediation-proposals`、`GET /api/v1/remediation-proposals/{id}`、`POST /api/v1/remediation-proposals/{id}/decision`（admin + CSRF，乐观锁，写审计日志 `remediation.approved/rejected`）。控制服务定位规则：purpose=iot 且目录含 `decide_remediation_proposal`（approval_required）的服务。
- Agent 运行时指令升级为闭环剧本，`max_turns` 8→14；`process_agent_run` 把 `create_remediation_proposal` 的结果写入 assistant message metadata（`remediation_proposals`），前端据此渲染审批卡并在刷新后恢复。

## 9. 案例自动沉淀（v1.1，v1.2 起改为事件驱动）

控制面与诊断面之间不做服务间调用，案例沉淀完全通过 MQTT 事件解耦：

- Control MCP 在恢复验证收敛后向 `iot/{device_id}/remediation` 发布完成事件（QoS1）：`{event: completed, command_id, proposal_id, device_id, action, parameters, reason, status, verify_status, ack, diagnosis_id, issued_by}`。它不关心谁在消费。
- 诊断服务订阅该主题（持久会话，重启不丢事件），`verify_status=succeeded` 时关联诊断记录：优先用事件携带的 `diagnosis_id`；缺失时按设备 + 时间窗（`DIAGNOSIS_REMEDIATION_CORRELATION_MINUTES`，默认 60 分钟）兜底取最近一次成功诊断。
- 案例由诊断服务写入自有存储（fault_type/fault_name/cause/evidence 来源于诊断，solution 记录实际执行动作、设备回执与验证结论，`verified_by=auto-remediation:{command_id}`），随后向 `iot/{device_id}/remediation_case` 回发确认 `{command_id, device_id, case_id, diagnosis_id}`。
- Control MCP 订阅确认主题，把 `case_id` 关联回命令行（`case_status: pending -> archived`），前端审批卡据此显示沉淀结果。
- 依赖方向：Control 对 Diagnosis 零感知（只依赖 MQTT 主题契约）；Diagnosis 拥有案例库的所有权。

## 10. 安全

- `CONTROL_MCP_BEARER_TOKEN` 保护 `/mcp`（与诊断服务共用同一 token 配置）。
- 高风险动作的人工批准必须走后端 REST（admin + CSRF + 审计），提案带乐观锁与过期时间，防重放与误执行。
- Agent 的工具目录由后端策略决定；`decide_remediation_proposal` 因 `approval_required` 策略天然对 Agent 不可见。
