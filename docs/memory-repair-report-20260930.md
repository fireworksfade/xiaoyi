# Memory 修复与复验报告

> 历史范围说明（2026-10-01）：本报告保留当时的验证结果。当前项目已移除 MySQL 依赖、迁移、镜像重建及相关测试；其中的 MySQL 记录和旧重建命令不代表当前支持范围。当前业务数据库使用 SQLite，知识向量使用 Qdrant。

日期：2026-09-30（Asia/Shanghai）

对应规格：`memory-replacement-spec.md` v1.2

原始问题：[独立复验报告](memory-reacceptance-report-20260930.md)；代码基线 `4a30607`，本报告涵盖 memory 修复与后续前后端联调。

## 结论

独立复验发现的 F01–F09 和附带的实现、验证缺口已修复，本轮撤回的 AC05、AC12、AC16、AC18、AC25、AC32、AC34、AC35、AC36、AC37 恢复完成勾选。其余 AC 沿用原有实现证据并通过相关全量回归。37 项 AC 在本轮功能验收范围内通过。

这不代表已完成 10,000 条记忆的性能压测，也不代表真实 LLM 的随机推理质量得到保证。确定性模型/工具桩、真实 HTTP/数据库/worker、真实 MySQL 和真实语义模型分别验证各自范围，不混写为同一种端到端证据。

## 实现修复与对应证据

| 问题 | 修复后行为 | 验证 |
| --- | --- | --- |
| F01 版本审核入口 | active 的待确认修订及 suspended 经验可查看正文、来源、新旧对照；确认使用已查看的 current_revision；首次点击先打开具体版本 | Vitest active/suspended 两种审核；浏览器旧版继续使用、新版确认及过期版本 409 |
| F02 反例暂停窗口 | 明确采用的经验遇到范围匹配的失败时，在结果事务内立即暂停并清理索引投影；候选修订异步生成 | 结果提交后、worker 执行前已停止召回；旧版本晚到反例不暂停已重新确认的新版本 |
| F03 未知结果放行 | pending 和 inconclusive 都阻止同服务、同设备新增修复；同名设备在不同服务下独立 | timeout、未知投递、追踪期限后的执行门回归 |
| F04 期限缺执行门 | 动作预留检查 Run 状态和期限；内部取证/再诊断每次调用重新检查状态、期限和持久工具预算 | 过期 Run 无预留；取消、并发 lease、固定预算回归 |
| F05 遗忘不撤回正文 | 移除失效证据关系并清空受影响历史版本正文；仅从仍有效的独立证据生成暂停、待审核版本；无支撑内容不能确认 | 多来源私有事实清除、独立事实保留和重新审核；浏览器 keep 后再 forget |
| F06 可选记忆故障阻断 | 来源、使用反馈、召回、工作记忆、终态捕获入队各自隔离失败；动作结果和预算仍持久化 | 故障注入后失败结果、再诊断及 Run 完成均保留 |
| F07 旧向量加分 | 保留向量 payload，并核验 owner、状态、revision、content_hash、模型指纹；晚到旧投影按原 revision 清理 | 旧版本、错 hash、错指纹拒绝；正确当前版本可召回 |
| F08 用户暂停被撤销 | 晚到事实更新不撤销用户暂停状态 | 暂停后晚到结果仍不可召回 |
| F09 状态未接 UI | 消费再诊断开始/完成/停止/晚到结果事件；显示已用次数；记忆活动显示候选、处理故障和需后续诊断的结果 | hook/UI 回归；后续诊断按钮填写新会话请求，由用户发送 |

附带修复：

- 召回不等于采用。设备动作通过 `applied_memory_refs` 明确关联已检索、仍有效的经验版本；真实 command 出现后才记录 applied。首次动作也支持此关联。
- 超时后的明确终态可更新同一反馈，避免 inconclusive 永久遮住后来失败；重复结果不重复累计。
- 恢复验证成功后，同一 Run 不再自动对同服务、同设备发起修复。
- 再诊断上下文包含原动作理由，以及可取得的、按 owner 和服务核验的前次诊断正文，保留失败事实与剩余预算。
- 删除正文有到期任务及周期补扫，覆盖旧删除记录；执行结果留在业务记录，记忆清理不下发新设备动作。
- 待审核筛选和数量包含已启用/暂停记忆的候选修订，排除已拒绝修订。
- 失败记忆任务提供受 owner/CSRF 保护的人工重试入口；重复点击不能重置已运行任务。
- 重新打开详情会刷新版本及来源状态；展示必要摘录和内容 hash。
- 知识库文案改为旧案例已退役；修复已有测试中的三处类型 lint。
- Qwen reranker 只使用 forward logits，显式提供 `GenerationConfig`，避免加载仓库的 custom generate 代码导致服务启动失败。模型服务恢复 ready 后完成真实在线评估。

## 实际验证结果

| 检查 | 结果与范围 |
| --- | --- |
| backend 全量 pytest | 最新 149 passed、1 skipped，69.50 秒；memory 定向套件 44 passed，7.31 秒 |
| 真实 MCP 传输发现 | 1 passed，2.51 秒；仅发现工具，不执行设备动作，补跑全量套件中跳过的项目 |
| mcp-services 全量 pytest | 联调后最新 150 passed、5 skipped，11.48 秒；此前启用专用 MySQL 时为 152 passed、3 skipped，16.66 秒，含两个真实 MySQL 用例；三个既有旧 rebuild 用例仍显式跳过 |
| 真实 MySQL 重验 | 2 passed，2.69 秒；MySQL 8.4.11，独立端口 13316，随机测试数据库，测试后删除；空库升级、旧文档/设备保留、部分 DDL 中断和重复升级 |
| 前端 typecheck / lint | 均通过 |
| 前端 Vitest | 8 文件、34 tests passed；候选正文、active/suspended 新版确认、后续诊断入口及修复事件 |
| 前端 build | 通过，Vinext 完成全部构建阶段 |
| Playwright | 最新 2 passed，26.8 秒；既有会话 mock 流程 + 经真实前端同源代理的后端记忆流程 |
| 在线语义评估 | 真实 Qwen3-Embedding-0.6B、512 维、Qdrant；4/4 同义查询首位命中；外部用户/不适用服务设备条目全部排除；测试 collection 已删除 |
| portable 降级评估 | 同一固定数据集，关闭 embedding 后，4/4 中文关键词查询首位命中，mode=keyword |
| Python 静态检查 / diff | 修复文件的 Ruff 检查通过；`git diff --check` 通过 |

运行环境为 Windows/PowerShell、Python 3.14.7、Node/npm workspaces。后端沿用独立 `.tmp/memory-acceptance-20260930/venv`，未修改原有不兼容的虚拟环境。在线评估使用 NVIDIA GeForce RTX 3060 Laptop GPU（6 GiB 显存）；模型服务 `/ready` 报告 CUDA 和两个 Qwen 模型 ready。

浏览器记忆流程使用临时 SQLite、真实 API/版本事务、真实持久 worker；外部诊断和经验提炼由确定性桩提供。后续联调已移除 Playwright 请求转发，浏览器真正经过 13000 前端的 `/api/backend` 代理进入专用 18001 后端。测试禁用 Wrangler 的 `.env.local` 覆盖，并在发送消息前核验临时后端标记；记忆 API 不 mock、不拦截。覆盖捕获→候选不召回→查看→确认→修订时保留旧版→409→确认新版→新会话召回→删聊天 keep→再清除来源→删聊天 forget。晚到结果、用户暂停和终态不重启由后端固定事件测试覆盖。

在线评估数据共 6 条，包含心跳断连、供电、磁盘、重连失败经验，以及跨用户同名条目和不适用服务设备条目。英语同义表达对应中文内容，避免把关键词命中误报为语义检索；最近一次查询分别为 151.6、164.1、168.8、121.5 ms。这是小样本 warm 结果，不能外推 10,000 条规模的 P95。机器可读结果位于 `output/memory-acceptance-20260930/online-retrieval-result.json`。

## 测试期间的一次隔离配置错误

首次浏览器联调受到本地代理绑定影响，请求进入现有 8000 后端。该测试 Run 对 ESP32_05 执行了一次 `reconnect_mqtt`，命令 `CMD_20260929_8F328E5F` 结果为 succeeded。测试会话 `9174a03f-20f5-4246-9322-066821de7d83` 及其派生记忆已清除，业务命令记录保留。已向用户说明此事。随后固定转发至隔离后端；最终通过的流程不连接现有设备服务。

## 复跑入口

- 后端：在 `packages/backend` 执行 `python -m pytest -q`；实服务发现可单独设置 `MCP_INTEGRATION_URL=http://127.0.0.1:9000/mcp` 后运行 `tests/integration/test_mcp_transport.py`。
- MySQL：只针对专用测试服务设置 `MYSQL_ACCEPTANCE_PORT`，在 `packages/mcp-services` 执行 `python -m pytest tests/test_memory_mysql_acceptance.py -q`。
- 前端：`npm run typecheck`、`npm run lint`、`npm run test`、`npm run build`。
- 浏览器：设置 `E2E_MEMORY_LIVE=1` 和可用的 `E2E_PYTHON`，执行 `npm run test:e2e`；自动启动 13000 前端与 18001 临时后端。
- 语义评估：模型 9010 与 Qdrant 6333 ready 后，在 `packages/backend` 执行 `python scripts/evaluate_memory_retrieval.py --output <结果文件>`；创建并清理独立测试 collection，不读写正式记忆。

后续按用户要求重启本地后端/MCP 加载修复，启动 3000 前端；同源代理和 localhost 跨域联调均通过，消息禁用设备工具。首轮外部模型流连接中断，重验成功。MCP 动作工具目录已核验包含 `applied_memory_refs`。本次没有执行新的正式数据库迁移；发布部署和规模性能验证仍是独立工作。
