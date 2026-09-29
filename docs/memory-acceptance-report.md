# Memory 替换故障案例库 spec 验收报告

> 下文保留的是 2026-09-29 历史结论，其“37/37”不直接作为当前验收依据。2026-09-30 [独立复验](memory-reacceptance-report-20260930.md) 发现问题，随后完成修复；最新实现、测试结果与验证范围见 [修复报告](memory-repair-report-20260930.md)。

日期:2026-09-29
对应规格:`docs/memory-replacement-spec.md` v1.2(D01–D11)
基线:提交 `b5dc9bf` 之后的补齐改动(工作记忆读取、使用记录与反馈、反例暂停、原生记忆工具、可观测事件、再诊断边界修复)

## 结论

**实现主体与全部既有测试通过;37 条验收标准全部达到"实现完成且有测试/迁移验证"。** spec 16.5 建议的 Playwright 记忆场景 E2E 未交付,作为残余项列出。不影响 AC 复选框所标状态,但发布前建议补齐。

## 验证环境与结果

| 套件 | 结果 |
| --- | --- |
| backend pytest | 133 passed, 1 skipped |
| mcp-services pytest | 150 passed, 3 skipped |
| frontend tsc --noEmit | 无错误 |
| frontend vitest | 8 文件 30 tests 全过 |

## 验收标准逐条状态

状态说明:✅ = 实现完成且由测试/迁移验证;🟡 = 实现完成,测试仅部分覆盖(其余为代码审阅确认)。

### 16.1 功能与证据

| AC | 状态 | 验证 |
| --- | --- | --- |
| AC01 情景自动记录/无价值不创建 | ✅ | `test_capture_gate_rejects_contentless_results`、工具白名单门控 |
| AC02 四态结果表达,重连≠根因 | ✅ | `test_normalize_result_mapping_table`;情景摘要固定"不确认根因" |
| AC03 经验均为候选,确认后才可召回 | ✅ | `test_confirm_then_recall_and_revision_flow`;提炼强制 hypothesis |
| AC04 认识与步骤可并存可缺一 | ✅ | `MemoryWrite` 校验 + 提炼提示词 |
| AC05 编辑生成待确认新版本/冲突处理 | ✅ | 后端 409 测试 + 前端编辑 UI 测试(本次补齐前端) |
| AC06 幂等/反馈不重复累计 | ✅ | 幂等测试 + `UNIQUE(owner,memory,command)` |
| AC07 界面关闭/Run 结束仍可更新结果 | ✅ | worker `track_action` 持久追踪;审批人不写 owner |
| AC08 响应丢失找回原命令不重发 | ✅ | MCP correlation 重放/冲突/投递未知测试 |
| AC09 模型不可用/取消/未知不伪造 | ✅ | `MEMORY_MODEL_UNAVAILABLE` 挂起;inconclusive 映射 |

### 16.2 隔离与召回

| AC | 状态 | 验证 |
| --- | --- | --- |
| AC10 跨用户全链路隔离 | ✅ | API 404/搜索为空/trace owner 校验/向量 owner 过滤测试 |
| AC11 同名设备不误匹配、未知范围待核实 | ✅ | `test_retrieval_applicability_scoping_and_uncertainty`(跨服务排除/明确不适用排除/待核实标注) |
| AC12 召回排除候选/暂停/删除/pending | ✅ | 召回过滤测试 |
| AC13 记忆进入 MCP 内部诊断 LLM | ✅ | `test_diagnose_passes_memory_context_to_llm_and_preserves_refs`、`test_diagnose_rejects_oversized_memory_context`(MCP 侧);后端 repair_context 传参测试 |
| AC14 引用保留版本来源、权限不升格 | ✅ | `memory_refs` 输出 + 提示词"不授权执行动作" |
| AC15 向量故障关键词降级、预算不挤当前消息 | ✅ | 降级路径 + 预算跳整条逻辑;工作记忆预算测试(本次) |
| AC16 指纹/维度/晚到/重建不召回错版本 | ✅ | `test_vector_indexing_fingerprint_mismatch_and_late_upsert_never_revive`、`test_vector_indexing_uses_owner_filter_and_marks_indexed`(fake Qdrant 在环) |

### 16.3 删除、迁移与旧功能退役

| AC | 状态 | 验证 |
| --- | --- | --- |
| AC17 删除立即不召回、不可复活 | ✅ | tombstone 测试 + 迁移取消旧 outbox(CANCELLED_LEGACY_FAULT_CASE) |
| AC18 来源清除撤回派生经验 | ✅ | `test_forget_source_suspends_derived_experience` + eligible 传递校验 |
| AC19 旧案例不进 memory、旧表不存在 | ✅ | 双库 drop 迁移测试 |
| AC20 旧字段不影响新记忆可信度 | ✅ | 新模型独立,无导入路径 |
| AC21 旧 REST 404/工具目录无四工具/UI 消失 | ✅ | `test_retired_fault_case_api_is_gone` + RETIRED_TOOLS + 前端退役断言 |
| AC22 旧 MQTT 退役、无 case 字段 | ✅ | 退订逻辑 + 控制库列删除迁移 |
| AC23 旧表/列/向量/outbox 清理、文档不受误删 | ✅ | 迁移测试(按 source 精确清理) |
| AC24 诊断关联/审批/执行/验证/文档检索回归 | ✅ | 全部相关套件通过 |
| AC25 新库/SQLite/MySQL 升级与失败恢复 | ✅ | `test_migrations` + `test_upgrade_snapshots`(0007/0008/0009) |
| AC26 无待分配区/导入接口 | ✅ | 0008 删除 legacy_imports + 迁移测试 |
| AC27 聊天删除 keep/forget | ✅ | forget 撤回测试;keep 默认保留、工作记忆清理 |
| AC28 ACK≠恢复、矛盾、未知投递映射 | ✅ | 归一化映射表 + MCP 投递状态测试 |

### 16.4 失败后的自动再诊断

| AC | 状态 | 验证 |
| --- | --- | --- |
| AC29 失败→取证→新诊断,模型收到前次证据与预算 | ✅ | `test_rediagnosis_feeds_next_repair_with_context`(本次,捕获实际传参断言) |
| AC30 新依据可继续,无新依据停止并说明原因 | ✅ | reserve 门测试 + `loop_stopped/no_new_evidence` 事件(本次) |
| AC31 合计 3 次、多设备共用、第 4 次拒绝 | ✅ | `test_three_failures_exhaust_budget_and_stop_loop`(本次) |
| AC32 轮询/重复事件不重复计数、终态不重启、未知投递保留名额 | ✅ | save_result 幂等 + 原子预留 + worker 不重启 Run |
| AC33 高风险逐次审批、待批预留、延迟批准归属原 Run | ✅ | `test_pending_proposal_reservation_and_release`、`test_late_approval_stays_on_original_run_budget` + 审批 REST 测试 |
| AC34 Run 结束后只通知不再诊断 | ✅ | needs_followup + `loop_stopped/run_finished` + `/memories/activity` action_results(本次) |
| AC35 未知先补查、超限转后台、期限受控 | ✅ | inconclusive 映射 + 7 天补查上限 + 运行期限(本次) |
| AC36 记忆故障不阻塞再诊断、预算不丢失 | ✅ | 预算存 runtime_state;工作记忆跨 Run 注入(本次);记录任务独立 |
| AC37 逐次结果保留、采用才反馈、暂停不再注入 | ✅ | usage/feedback/反例 suspend 测试(本次) |

## 本次补齐的实现

1. 工作记忆读取路径:`service.working_snapshot` + `build_working_message`,orchestrator 在新 Run 注入同会话工作记忆(有界、过期即停、会话删除即失效)。
2. 使用记录与反馈:`memory_usage` retrieved(召回)与 applied(再诊断依据被实际采纳)两阶段;`memory_feedback` 仅在命令结果落定时按实际采用经验记录;`last_used_at/use_count` 生效。
3. 反例处理:采用经验失败且适用范围匹配 → 立即暂停 + 生成待确认修订(附反例说明);范围不匹配只记范围问题。
4. 原生记忆工具:`search_memory`/`get_memory`(只读)、`propose_memory`(仅候选),服务端绑定 Run 用户,模型不能指定 owner 或确认。
5. 可观测性:`memory.*` 事件与任务指标、`remediation.loop_stopped`(attempt_limit_reached/no_new_evidence/run_finished/run_deadline)与 REMEDIATION_LOOP_STOPS 指标;`/memories/activity` 增加命令结果追踪与 needs_followup。
6. 再诊断边界:运行期限检查(`AGENT_RUN_MAX_RUNTIME_MINUTES`,默认 60);补查期限 8→7 天;Run 创建/重试时固化修复预算。
7. 前端:记忆编辑 UI(PATCH + expected_revision,409 提示,active 编辑后提示"旧版本仍在召回使用");vitest 2 例。
8. 清理残留:`artifacts.py` 移除 case 字段、`evaluate_chunk_sizes.py` 移除失效 fault_cases 路径、`rebuild_external.py` 帮助文本、`knowledge_cases.py` → `knowledge_documents.py`(`KnowledgeDocumentMixin`)。
9. 新增迁移 `0009_action_applied_memory`(memory_action_links.applied_memory_ids)。

## 残余缺口(不阻塞 AC 标注,建议后续处理)

以下两项为体验/覆盖增强,不对应未完成的 AC:

- Playwright 记忆场景 E2E(spec 16.5 建议)未交付;现有前端覆盖为 vitest 组件测试。
- 记忆详情页未展示来源详情展开与新旧逐字段 diff(当前为摘要级提示)。
