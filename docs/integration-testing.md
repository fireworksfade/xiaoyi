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
