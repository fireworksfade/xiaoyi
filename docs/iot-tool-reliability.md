# IoT 工具可靠性与验收

设备命令、审批与待投递记录在同一 SQLite 事务中提交。MCP 工具的 `ok=true`
表示请求已受理；是否发送、设备是否执行以及修复是否有效分别查询命令字段。

## 投递状态

`delivery_status` 的取值：

| 状态 | 含义 |
| --- | --- |
| pending | 待投递，MQTT 尚未连接时保留并每 5 秒尝试；队列有效期 30 分钟 |
| dispatching | 已领取投递，正在向 MQTT 发送 |
| broker_confirmed | 收到 QoS1 PUBACK，仅表示 Broker 确认 |
| device_acked | 收到匹配设备与命令 ID 的执行回执 |
| unknown | 发布结果不明或发送中服务重启；不自动重发 |

`delivered=true` 只在 Broker 已确认或设备已回执时返回，不能据此声称修复成功。
审批时 MQTT 未启用仍返回已提交的 approved 提案、命令 ID 和 pending 状态。
服务启动后恢复待投递队列。未知投递结果通过 `get_action_result` 跟踪；需要再次
执行时，应重新确认设备状态并基于新的诊断发起动作。

等待设备回执的超时从 Broker 确认/未知发送时开始计算；从未发送的命令按队列
有效期过期。下行载荷包含 `expires_at`，设备应拒绝过期命令。模拟器已实现该检查。
QoS1 允许网络层重复交付，实际设备端仍应按 `command_id` 去重。

## 恢复验证

回执与观察窗口原子落库；每条命令独立保存窗口，重启后继续验证。新的非 retained
设备状态才作为证据；早于回执、非法或明显来自未来的时间戳不会参与验证。
观察窗口内出现 ERROR/CRITICAL 日志判失败。

| 动作 | 成功条件（均要求新状态 online=true） |
| --- | --- |
| reconnect_mqtt | mqtt_status=connected |
| reconnect_wifi | wifi_status=connected 且 rssi≥-75 dBm |
| calibrate_sensor | sensor_valid=true、sensor_calibrated=true 且 temperature 为有效数值 |
| set_reporting_interval | reporting_interval_seconds 等于目标 seconds |
| restart_device | uptime 为非负数且低于执行前快照 |
| update_firmware | firmware_version 等于目标 version |

未上报所需字段或缺少执行前快照时，`verify_status=inconclusive`，不会计为成功
或明确失败。前端显示“验证证据不足”，记忆模块按结果不明处理。传感器和上报间隔
的额外状态字段已由模拟器提供；实际设备需实现相同字段才能完成相应验证。
动作目录目前按已实现的 ESP32 协议过滤设备类型，不推测未提供的固件版本能力。

## 升级与工具目录

新增控制库迁移 0005；已有命令标记为 unknown，禁止重新入队，未完成的验证以
无证据窗口恢复。迁移不修改历史脚本。开发 Compose 启动命令自动执行迁移：

```powershell
docker compose restart backend iot-mcp iot-simulator-fleet
docker compose exec -T backend python scripts/bootstrap_local_mcp.py
```

检索模型覆盖文件继续使用原有组合。单独运行 MCP 时先执行
`python -m scripts.migrate upgrade --service control`，然后启动服务。
刷新工具目录会因参数 schema 变更暂时禁用受影响工具，注册脚本重新应用既定策略。

工具现包含分页、日志级别、知识源、检索策略、动作枚举和参数数量校验。
设备/知识文档列表在 SQL 中过滤、聚合和分页；响应不读取全部正文到 Python。
诊断输入错误不可重试；数据库、检索和其他执行错误分开报告，能够保存失败诊断时
返回 diagnosis_id，供 `get_diagnosis_trace` 查询。

## 验证

本次回归：MCP 全量 305 项通过；后端独立 Docker 测试容器 158 项通过、1 项跳过；
前端全量 55 项通过，类型检查、lint 和构建通过。真实本地 MQTT 冒烟使用唯一
虚拟设备与临时数据库，验证 PUBACK、设备回执、状态采样及持久验证结果：

```powershell
# 在 packages/mcp-services 目录内，使用已安装项目依赖的 Python
python -m tests.mqtt_control_smoke --host 127.0.0.1 --port 1883
```

2026-10-07 已在本地运行环境应用：按原有 `compose.yaml` 与
`compose.retrieval-api-fallback.yaml` 组合重启 backend、iot-mcp、iot-simulator-fleet，
宿主机前端单独重启。控制库迁移状态为 head=5、pending=[]；注册脚本确认 MCP
连接正常、发现 19 个工具，并按既定策略启用 17 个工具。

前端页面、后端 `/ready`、MCP `/ready` 和前端同源代理 `/api/backend/ready` 均返回
HTTP 200。通过后端实际调用 MCP 验证了设备最新状态、新动作枚举、六类动作的参数
schema/验收说明及 SQL 分页。本次重启未重复执行此前的付费模型浏览器联调。

迁移前通过 SQLite backup API 将控制库备份到持久数据卷：
`/app/data/iot_control.before-tools-20261007-b0687581.db`。备份与本地前端日志不提交到 Git。
