# 前后端联调

在仓库根目录配置 `.env` 中的 Text2SQL / 诊断模型、主 Embedding / Reranker API 和本地兜底服务。聊天主模型沿用前端“设置”保存的配置。真实 API 密钥只放在服务端配置中。

```powershell
docker compose -f compose.yaml -f compose.retrieval-api-fallback.yaml up -d
python packages/backend/scripts/bootstrap_local_mcp.py
npm run dev
```

前端地址为 `http://127.0.0.1:3000`，通过 `/api/backend` 代理访问后端。确认前端 `packages/frontend/.env.local` 中的 `BACKEND_BASE_URL=http://127.0.0.1:8000`。

聊天首页提供“查询节点历史数据”。也可输入“统计过去24小时各节点平均温度和有效样本数”，展开 `query_iot_data` 查看表格、设备范围、时间范围、指标口径、截断提示及 SQL/绑定参数。无数据时显示空结果，不把空采样当成正常状态。工具失败、需要澄清及仍在运行分别显示对应状态。

展开 `search_knowledge` 可以查看引用来源和实际使用的向量检索/重排服务；发生降级时显示“已使用兜底”。对话消息 API 从已有运行事件恢复工具输出和工件引用，因此刷新、切换对话或加载更早消息后仍能展开结果；完整工件仍受现有访问控制和保留期限制。

## 检查命令

```powershell
npm run typecheck
npm run lint
npm test
npm run build
npm run test:e2e -- --workers=1
```

默认浏览器回归使用模拟网络，不调用付费模型。真实联调需要正在运行的服务、有效聊天模型和诊断模型配置，以及三套现有索引：

```powershell
$env:E2E_IOT_LIVE='1'
npm run test:e2e -- --workers=1 e2e/iot-live.spec.ts
```

真实联调检查自然语言历史查询、SQL 表格与刷新恢复、API 主检索引用及状态、无掉线事件口径时的澄清。另通过知识文档界面上传一个唯一临时文档、使用相同 ID 替换内容、删除文档，并直接检查 API（1024 维）、Qwen（512 维）、hash（384 维）三个 Qdrant 集合的内容与索引。测试只清理自己创建的临时文档，保留查询对话供查看。

若集合改名，按 API、本地、hash 顺序设置 `E2E_QDRANT_COLLECTIONS`（逗号分隔）。本机默认使用 `iot_diagnosis_dashscope_qwen37_flash_1024,iot_diagnosis_qwen3_512,iot_diagnosis_portable`。不同浏览器测试进程应使用不同的 `--output` 目录，避免互相清理 trace。

Text2SQL 计划格式错误（包括无法解析的模型 JSON）最多纠正一次，仍须经过相同白名单和只读执行校验；设备范围冲突和业务口径不明确直接要求澄清。设置 `MCP_AGENT_TIMEOUT_SECONDS` 时须覆盖两次 `DIAGNOSIS_LLM_TIMEOUT_SECONDS` 加数据库执行/通信时间；单次模型超时 90 秒时可设为 210 秒。模型服务可能有波动，失败会明确展示，不执行未经校验的 SQL。

本地模型写入失败后，hash 仍继续更新；本地恢复后的索引补齐沿用 [重建说明](retrieval-api.md)，不会由前端自动触发重建。

## 六种修复动作联调

`e2e/iot-actions-live.spec.ts` 覆盖 MQTT 重连、WiFi 重连、传感器校准、上报间隔调整、设备重启和固件升级。需要上述服务（含 `toxiproxy` 与已构建的 `xiaoyi-esp32-node:local` 镜像）及有效聊天/诊断模型配置；测试会调用已配置的模型 API。

在仓库根目录执行：

```powershell
$env:E2E_IOT_ACTIONS_LIVE='1'
npm run test:e2e -- --workers=1 e2e/iot-actions-live.spec.ts
Remove-Item Env:E2E_IOT_ACTIONS_LIVE
```

每项测试通过 `docker compose run esp32-node` 启动一台唯一命名的 QEMU ESP32，运行真实 xiaoyi-node 固件，并为它单独创建一个 Toxiproxy 代理。故障均为真实发生：`mqtt_timeout` 通过 Toxiproxy 双向黑洞让设备 Keep Alive 超时（`No PING_RESP`），设备断开后 Toxiproxy 同步关闭 Broker 一侧连接；传感器、内存泄漏和看门狗由固件 `inject_fault` 演练产生。随后通过真实页面发送请求，让 Agent 调用诊断与修复 MCP 工具。四种低风险动作直接执行；两个高风险动作先检查待审批时没有命令，再点击页面“批准执行”。随后确认设备回执、`device_acked` 和最终 `verify_status=succeeded`，并验证刷新后的工具输出与审批卡片恢复。

`reconnect_wifi` 在 QEMU 中跳过：QEMU 没有 WiFi 射频，该动作在 Wokwi 中验证（见 [ESP32 设备仿真](../packages/esp32-node/README.md)）。

测试使用真实 MQTT Broker 和服务的完整观察窗口，通过只读查询控制库核对结果；不伪造回执或验证状态，也不提前推进验证时间。测试结束停止自己启动的设备、删除其代理和 flash 镜像，保留联调对话、诊断和命令记录。截图、工具输出、命令证据和设备串口日志保存在 Playwright 输出目录中。

## 2026-11-12 验证结果（QEMU 真实固件）

设备端换成 QEMU 中运行的 xiaoyi-node 固件（ESP-IDF v5.5.4）后重新联调。

| 检查 | 结果 |
| --- | --- |
| 六种修复动作浏览器端到端测试 | 5 通过、1 跳过（`reconnect_wifi`，QEMU 无 WiFi 射频），约 10.4 分钟 |
| 固件编译 | QEMU 与 Wokwi 两个变体均编译通过，0 警告；Wokwi 变体未在 Wokwi 中运行 |
| `restart_device` | 回执 `applied`，重启后 `reset_reason=SW`，持久会话 `session_present=1` |
| OTA 1.3.1 → 1.4.0 | 下载 601 KB 写入 `ota_1`，重启后连上 Broker 即确认有效 |
| OTA 回滚 1.4.0 → 1.4.1-rc1 | 自检失败并 `abort()`，引导程序回滚到 1.4.0，上报 `panic_reset` 与 `ota_rollback` 两条故障 |
| `inject_fault` panic | `reset_reason=PANIC`，core dump 摘要含任务 `panic_drill`、`EXCCAUSE 29` 与回溯 |
| `inject_fault` watchdog_reset | `reset_reason=TASK_WDT`，故障含 panic 原因“IDLE0 (CPU 0) 未按时喂狗”与回溯 |
| Compose 机群 9 台 | 全部在线；esp32-04 堆泄漏、esp32-08 看门狗崩溃循环、esp32-09 传感器失效、esp32-10 每 4 分钟断开重连均真实发生 |
| MCP 测试 | 288 通过 |

## 2026-11-12 运维问题复现（记忆种子来源）

为整理记忆种子（`packages/backend/seed/ops_memories.json`），在 QEMU 中用 `OPS_*` 临时设备逐一复现能出现的运维问题。每台设备单独使用一个 Toxiproxy 代理。故障来源只有三种：Toxiproxy 网络故障、固件 `inject_fault` 演练、真实的 Broker 或电源操作。诊断和命令都通过 IoT MCP 下发，没有伪造回执。下表的诊断与命令记录保留在平台库中，可以按 ID 查询。

| 问题 | 设备 | 处置与结果 |
| --- | --- | --- |
| 升级 1.4.0 后看门狗崩溃循环 | OPS_WDT | `rollback_firmware` 回到 1.3.1，验证成功（`CMD_20261112_454D1E30`） |
| 出厂固件看门狗崩溃循环 | OPS_WDT2 | 另一分区没有旧固件，回退被拒绝。在线时下发升级，下载中途被复位打断。改在设备刚复位时下发，升级成功（`CMD_20261112_EA436C63`，回执约 43 秒） |
| 1.2.0 慢速内存泄漏（约 51 B/s） | OPS_LEAK | 重启只能推迟；升级到 1.3.1 后堆内存保持平稳 |
| 传感器读取超时 | OPS_SENSOR | 校准后恢复，重新上电后复发，升级后解决 |
| 升级到不存在的版本 9.9.9 | OPS_OTA | 设备日志显示 HTTP 404，回执 `ESP_FAIL` |
| 候选版本 1.4.1-rc1 自检失败 | OPS_OTA | 引导程序自动回滚，升级命令验证失败 |
| 单次 StoreProhibited panic | OPS_OTA | 只诊断不处置，设备自行恢复 |
| 上行中断 / 断电 2 分钟 | OPS_NET | 离线期间的命令在平台记为超时，恢复后被设备执行 |
| 链路每 4 分钟被对端断开 | ESP32_10 | `reconnect_mqtt` 回执成功，但验证失败，需要交给网络侧处理 |
| 4–8 秒延迟导致 `No PING_RESP` | OPS_LAT | 新动作 `set_mqtt_keepalive` 把 Keep Alive 从 10 秒改为 60 秒，之后不再出现 |
| 两台设备使用同一 ID | OPS_DUP | 3 分钟内重连 12 次，Broker 日志显示 `session taken over`，在现场停用重复设备 |
| 上报间隔 300 秒导致误判离线 | OPS_INT | `set_reporting_interval` 改回 30 秒 |
| 以太网节点执行 `reconnect_wifi` | OPS_INT | 只能重启网口，验证结果不明 |
| Broker 停机 2 分钟 | 全机群 | Broker 恢复后 27 个客户端会话全部恢复 |

复现过程中修复了以下问题：

- 升级命令的回执超时延长到 300 秒，其余动作仍是 30 秒。
- 以太网节点不再沿用旧的 RSSI 和 WiFi 状态。
- OTA 下载中断后，写了一半的分区不再作为 `rollback_version` 上报。
- 诊断规则不再把普通的“MQTT + 超时”当作 Keep Alive 问题，同时补充了看门狗、panic、内存不足和传感器读取失败的规则。
- 平台收到长度为 0 的 retained 清除消息时不再报错。

新增修复动作 `set_mqtt_keepalive`（低风险）和 `rollback_firmware`（高风险，仅当状态带 `rollback_version` 时可用），协议见 [设备协议](device-protocol.md)。MCP 测试 303 项通过，后端测试 159 项通过、1 项跳过。

WiFi 断开原因码和 NTC 开路/短路需要 Wokwi 才能复现，相关两条经验在种子中只作为待确认候选。场景配置在 `packages/esp32-node/wokwi/`（见 [ESP32 设备仿真](../packages/esp32-node/README.md)），需要用户自己的 Wokwi 许可运行。

### RAG 评测集

`packages/mcp-services/evals/rag_router.jsonl` 已改为 21 条用例，相关文档指向新的官方文档 ID。用例中的日志取自真实固件和 Mosquitto 的输出，覆盖 Keep Alive、对端重置、认证、看门狗、panic、堆内存、OTA 回滚、SNTP、WiFi 原因码和 ADC 校准。确定性档位（hash embedding + weighted 重排，不调用模型）的结果如下：

| 指标 | 结果 |
| --- | --- |
| 命中率 / recall@5 / MRR | 0.95 / 0.71 / 0.52 |
| 路由准确率 / 来源选择准确率 | 1.0 / 0.95 |
| 诊断类型 / 诊断名称准确率 | 1.0 / 1.0 |

为让评测符合真实日志，诊断规则做了三处修正：

- `Connection reset by peer` 不再被当作设备复位。
- Mosquitto 的 `has exceeded timeout` 归为 Keep Alive 超时。
- 新增“新固件自检失败已回滚”规则，放在 panic 规则之前。

路由原型补充了 PINGRESP、TLS、panic、回滚、HTTP 404 和 SNTP 等词。在 `packages/mcp-services` 中运行评测：先用 `python scripts/ingest_recommended_documents.py --database <临时库>` 导入文档，再执行 `python scripts/evaluate_rag.py --database <临时库>`。

## 2026-10-08 验证结果

本轮恢复既有 Docker 服务与宿主机前端，刷新 MCP 工具目录，使用已配置的真实聊天/诊断模型和检索服务完成联调。六种动作分别使用独立临时模拟设备，未操作既有机群设备。

| 检查 | 结果 |
| --- | --- |
| 六种修复动作浏览器端到端测试 | 6 通过，约 21 分钟，包含模型请求与完整观察窗口 |
| `reconnect_mqtt` | 设备回执 `applied`、投递 `device_acked`、验证 `succeeded` |
| `reconnect_wifi` | 设备回执 `applied`、投递 `device_acked`、验证 `succeeded` |
| `calibrate_sensor` | 设备回执 `applied`、投递 `device_acked`、验证 `succeeded` |
| `set_reporting_interval` | `seconds=3`，设备状态确认 3 秒，最终验证 `succeeded` |
| `restart_device` | 审批前无命令；页面批准后执行，运行时长降低，最终验证 `succeeded` |
| `update_firmware` | 审批前无命令；页面批准后执行，目标版本 `1.3.9`，最终验证 `succeeded` |
| 高风险审批卡片刷新恢复 | 两项均显示“设备已恢复，验证通过”，批准按钮不再出现 |
| 真实历史查询、知识检索、澄清及刷新恢复 | 1 通过 |
| 真实知识文档上传、替换、删除 | 1 通过，API/Qwen/hash 三套索引同步，临时文档已删除 |
| 基础聊天浏览器流程 | 1 通过，使用模拟网络 |
| 前端单元测试 | 55 通过 |
| 后端审批、诊断关联、工具执行、结果状态和能力路由测试 | 独立 Docker 测试容器内 20 通过 |
| MCP 控制、验收、模拟器、工具 schema 与参数校验测试 | 75 通过 |
| 前端类型检查、lint、生产构建 | 通过 |
| 前端、后端 `/ready`、MCP `/ready`、同源代理 `/api/backend/ready` | 均为 HTTP 200 |

历史查询首次刷新检查受到同账号另一联调进程新建对话的影响。测试已改为给自身对话设置唯一名称，并在刷新后明确重新选择该对话；重新运行通过。

本机验证证据保存在 `output/integration-20261008/`：`action-evidence.json` 包含六个命令、诊断关联与运行工具事件；六张按动作命名的 PNG 包含工具详情或已恢复的审批卡片。前端保留六个“2026-10-08 联调验证”对话供查看。该输出目录属于本机产物，不提交到 Git。

验证范围为真实软件服务与模拟设备的端到端链路。固件升级在模拟器中更新版本字段，传感器校准更新模拟状态；真实 ESP32 固件的命令执行、物理校准与 OTA 镜像下载安装仍需硬件验收。

## 2026-10-07 验证结果

| 检查 | 结果 |
| --- | --- |
| 前端单元回归 | 54 通过 |
| 后端完整回归 | 158 通过，1 跳过 |
| MCP 完整回归 | 263 通过 |
| 浏览器基础聊天流程 | 1 通过 |
| 真实 IoT / 知识文档浏览器联调 | 2 通过 |
| 前端类型检查、lint、生产构建 | 通过 |
| 历史温度查询 | 返回 12 个节点；表格、有效样本数和刷新恢复通过 |
| 真实检索切换 | API、本地 Qwen、hash/weighted、API 恢复四种路径通过 |
| 临时知识文档新增、同 ID 替换、删除 | 三套内容与向量索引均同步；测试文档已清理 |

检索异常通过独立验证进程内的 HTTP 调用拦截模拟，正常 API、本地模型与 Qdrant 均实际调用；未关闭或修改共享服务的网络。验证对话保留在当前项目中，可查看查询和引用结果。
