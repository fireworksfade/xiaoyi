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

`e2e/iot-actions-live.spec.ts` 覆盖 MQTT 重连、WiFi 重连、传感器校准、上报间隔调整、设备重启和固件升级。需要上述服务及有效聊天/诊断模型配置，还需要本机 Python 已安装 `packages/mcp-services` 的依赖；测试会调用已配置的模型 API。

在仓库根目录执行：

```powershell
$env:E2E_IOT_ACTIONS_LIVE='1'
$env:E2E_IOT_PYTHON=(Resolve-Path 'packages/mcp-services/.venv/Scripts/python.exe').Path
npm run test:e2e -- --workers=1 e2e/iot-actions-live.spec.ts
Remove-Item Env:E2E_IOT_ACTIONS_LIVE
Remove-Item Env:E2E_IOT_PYTHON
```

每项测试启动一台唯一命名的临时模拟设备，通过真实页面发送请求，让 Agent 调用诊断与修复 MCP 工具。四种低风险动作直接执行；两个高风险动作先检查待审批时没有命令，再点击页面“批准执行”。随后确认设备回执、`device_acked` 和最终 `verify_status=succeeded`，并验证刷新后的工具输出与审批卡片恢复。

测试使用真实 MQTT Broker 和服务的完整观察窗口，通过只读查询控制库核对结果；不伪造回执或验证状态，也不提前推进验证时间。测试结束停止自己启动的模拟设备，保留联调对话、诊断和命令记录。截图、工具输出、命令证据与模拟器日志保存在 Playwright 输出目录中。这些结果验证的是模拟设备链路，真实 ESP32 固件、物理传感器校准与 OTA 安装需要单独验收。

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
