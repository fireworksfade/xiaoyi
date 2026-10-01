# Memory spec 独立复验报告

> 历史范围说明（2026-10-01）：本报告保留当时的验证结果。当前项目已移除 MySQL 依赖、迁移、镜像重建及相关测试；其中的 MySQL 记录和旧重建命令不代表当前支持范围。当前业务数据库使用 SQLite，知识向量使用 Qdrant。

> 本文保留修复前的复验发现。本轮问题已修复，后续实现和验证证据见 [修复报告](memory-repair-report-20260930.md)。

日期：2026-09-30（Asia/Shanghai）

规格：`docs/memory-replacement-spec.md` v1.2，D01–D11、AC01–AC37 及正文要求
代码基线：`4a30607`，复验开始时 Git 工作区干净

## 结论

**验收未通过，不能维持原报告的“37/37 全部达到”。** 既有测试全部通过，但新增的 8 个后端探针均复现规格边界问题，3 个界面验收断言全部失败。测试通过只能证明已有断言成立，不能替代未覆盖的生命周期、遗忘和执行约束。

本次撤回 AC05、AC12、AC16、AC18、AC32、AC34、AC35、AC36、AC37 的完成勾选；AC25 标记为待实际 MySQL 验证。其余勾选沿用既有测试与审阅证据，本报告不宣称其全部经过真实服务端到端验证。

本次修改仅涉及验收文档及独立验证产物，未修复业务代码、未修改运行数据库、未向设备下发动作。

## 验证结果与环境

| 检查 | 实际结果 | 限制 |
| --- | --- | --- |
| backend pytest | 133 passed，1 skipped，68.55 秒 | 跳过真实 MCP transport，需要 `MCP_INTEGRATION_URL` |
| mcp-services pytest | 150 passed，3 skipped，13.44 秒 | 三项旧 MySQL rebuild 测试显式跳过 |
| 前端 typecheck | 通过 | `tsc --noEmit` |
| 前端 lint | **失败：3 处** | `memory-dialog.test.tsx:64,66,122`，`typescript(no-base-to-string)` |
| 前端 Vitest | 8 文件、30 tests 通过 | 不覆盖新版本确认、暂停后审核及具体内容展示 |
| 前端 build | 通过 | Vinext 构建完成 |
| 既有 Playwright | 1 passed，27.8 秒 | API 被 mock，仅覆盖登录/会话/SSE/重命名/删除；没有记忆跨会话流程 |
| 新增后端边界探针 | **8/8 复现规格违例** | 新建临时 SQLite；向量服务用 MockTransport；记忆故障用确定性注入 |
| 新增界面验收断言 | **3 failed** | 测真实 MemoryDialog，mock API；预期规格行为的断言失败 |

执行环境为 Windows/PowerShell、Python 3.14.7、本地 npm workspaces。原后端 `.venv` 中存在 cp312 的 `pydantic_core`，与 Python 3.14 不兼容，直接执行失败。为此在 `.tmp/memory-acceptance-20260930/venv` 创建独立环境并安装声明的 `packages/backend[dev]` 后复验，具体依赖见 `output/memory-acceptance-20260930/backend-environment.txt`。没有修改原虚拟环境。

Docker daemon 本次不可用，没有运行真实 MySQL 镜像升级、真实 Qdrant/embedding 服务联调、语义模型在线召回评估或性能规模测试。MySQL 迁移已有 `MagicMock` SQL 断言，不能将其写成已有数据的实库升级及失败恢复已经通过。

## 阻塞问题

### F01 · P1 · 已启用或暂停经验的修订无法在界面确认（AC05）

位置：`packages/frontend/features/memory/memory-dialog.tsx:136,269,305`。

当 `status=active,current_revision=2,active_revision=1` 时，界面只提示旧版本仍被使用，没有确认/拒绝新版本的按钮。`suspended` 的修订同样没有确认入口。按钮只在 `status=candidate` 显示。现有 `act()` 还优先发送 `active_revision`，若仅开放按钮，仍会确认旧版本并收到 409。

实际证据：`ui-probes.test.tsx` 的前两个断言均失败，确认按钮不存在。应为待确认修订及暂停后的审核提供具体版本查看与确认入口，使用 `current_revision`，同时展示新旧差异。

### F02 · P1 · 明确反例提交后仍可正常召回（AC05、AC37）

位置：`packages/backend/app/memory/actions.py:98,118,162`，`app/memory/reconcile.py:9`。

失败结果事务只写反馈及 `reconcile_experience` 异步任务，真正暂停发生在 worker 里。worker 未执行或失败时，该经验仍为 active；紧接着自动再诊断可再次召回它。

实际证据：`counterexample_remains_recallable_before_worker` 输出 `status=active,hits=1`。既有测试显式调用 `reconcile()` 后才检查暂停，因此漏掉了这个窗口。明确适用范围内的反例必须在结果事务中立即禁止召回，候选修订可异步生成。

### F03 · P1 · 未收敛/未知结果允许同设备新修复（AC32、AC35；§7.2–7.4）

位置：`packages/backend/app/memory/actions.py:48,58`。

执行门只阻止 `outcome=pending`，失败门只处理 `failed`。结果转为 `inconclusive` 后，两者都不适用，即使原动作仍占名额、投递未知，也可预留同设备的新动作。

实际证据：`timeout_allows_another_same_device_action` 和 `unknown_delivery_allows_new_action_after_tracking_deadline` 均获得新 reserved 名额；后一例原记录仍为 `outcome=inconclusive,reservation=reserved`。这些探针未实际下发设备动作，但确认后端执行前的预留门允许通过。应先只读恢复查询，明确旧命令已收敛或确实未下发后再允许新增动作。

### F04 · P1 · Run 期限不是动作执行门（AC35；§7.5）

位置：`packages/backend/app/memory/actions.py:37`，`app/memory/boundary.py:66`。

期限只在 `rediagnose()` 入口检查；`reserve()` 只检查 RUNNING 状态，不检查开始时间。一个已经超过运行期限、仍为 RUNNING 的 Run 可以获得修复名额，包括首次动作。

实际证据：`expired_run_still_reserves_device_action` 在开始时间早于期限 10 分钟时仍返回 reserved。应在设备操作的最后执行边界检查期限，并在取证/再诊断的后续步骤重新检查取消、期限及工具预算。

### F05 · P1 · 来源遗忘不清理派生正文，也不修订多来源经验（AC18；§9.3）

位置：`packages/backend/app/memory/service.py:274`，`app/memory/worker.py:30`。

`forget_source()` 清空来源摘录并暂停经验，但 `revalidate_dependents` 只暂停不合格 active 内容，以及清空超过 30 天的 deleted 正文。它不移除被撤回的证据关系，不清理 suspended 经验中的私有正文，也不根据其余有效来源创建待确认修订。

实际证据：`forget_does_not_revise_or_clean_derived_content` 在遗忘及后台 revalidate 后仍为 revision 1、证据关系 2 条，记忆详情仍可见 `FORGOTTEN_PRIVATE_FACT`。应保留无关有效证据、撤回被清除部分，并形成可审核的新版本。

### F06 · P1 · memory 写入异常会阻断当前再诊断（AC36）

位置：`packages/backend/app/agent/runtime.py:171`，`app/memory/boundary.py:37,52`。

Runtime 先 await `finish()`，随后才执行 `rediagnose()`。`finish()` 同步写 memory 来源/工作记忆/任务，未隔离这些操作的异常。记忆表写入故障会使工具调用抛错，当前原始失败事实无法进入下一次诊断。

实际证据：`memory_capture_failure_propagates_from_runtime_finish` 注入记忆持久化异常后，`finish()` 原样抛出 RuntimeError。应隔离非关键 memory 持久化失败，同时继续向持久化执行预算校验；不能把设备执行门的错误一并吞掉。

### F07 · P1 · 旧向量没有按版本核验，能给无关新内容加分（AC16）

位置：`packages/backend/app/memory/indexing.py:43`，`app/memory/retrieval.py:37,54`。

向量结果被压缩为 `memory_id -> score`，丢弃 hit 的 revision、content_hash 和 model_fingerprint。回 SQL 只核验当前 active 版本，没有核验向量实际对应的版本。旧点仍存在时，其旧语义分数被用于当前正文。

实际证据：`obsolete_vector_recalls_unrelated_current_revision`：只有 revision 1 的向量命中 `obsoleteonly`，SQL 当前确认的 revision 2 不含该查询且正文完全不同，最终仍召回 revision 2。应保留并校验 hit 版本/hash/指纹，拒绝失效点，并安排对应旧点清理。

### F08 · P1 · 晚到结果自动重新启用用户暂停的情景（AC12；§9.1）

位置：`packages/backend/app/memory/capture.py:95,100`。

自动捕获更新已有情景后，无条件将 `status,active_revision` 设为 `active,current_revision`。用户暂停后，只要同一来源得到新结果，就重新启用并进入正常召回。

实际证据：`late_episode_update_reactivates_user_pause` 输出 `status_after_late_update=active`。应区分规则激活与用户主动暂停，晚到事实可以更新但不能自动撤销用户的生命周期决定。

### F09 · P2 · 晚到结果与再诊断状态未接入用户界面（AC34；§10.3、§13.2）

位置：`packages/frontend/hooks/use-conversation-run.ts`、`components/remediation-card.tsx`、`lib/api/memory.ts`。

后端已有 activity 的 `needs_followup` 和再诊断事件，但前端没有调用 `/memories/activity`，没有处理 `remediation.rediagnosis_started/completed/loop_stopped/result_updated`，也没有“正在重新诊断”、次数或“需要发起后续诊断”的相应展示入口。修复卡片的失败标签仅显示“恢复验证失败”。不能把“API 返回通知字段”标成“用户已经收到提示”。

此项为入口及引用链代码审阅结果，尚未增加专用浏览器断言。

## 其他必须补齐的正文与验证要求

- **具体候选内容审核缺失（§10.3）**：详情展开只有摘要和索引状态，不展示 claims、procedure、适用条件、限制和来源。第三个 UI 断言确认实际处理步骤不可见。修改已启用经验时也没有新旧内容 diff。
- **检索被当成实际采用（AC37、§5.3/7.6）**：`actions.reserve():74` 将再诊断召回的全部 `rd.memories` 写为 applied；没有对“该动作实际使用了哪些经验”作确认。首次修复路径反而不记录这些关联。这个问题由代码审阅确认，探针中的反例场景手动建立 applied 关联，只用于验证立即暂停，不代表实际采用判定已正确。
- **删除保留期限缺少定时清理（§9.2）**：正文清理只在一次 `revalidate_dependents` 执行时检查“已删除超过 30 天”；该任务通常删除后立即完成。没有期限到达后的重排任务或周期扫描，长期无新撤回事件的用户可能一直保留已删除正文。现有通用 retention 未覆盖 memory。
- **MySQL 实库验证不足（AC25）**：SQL Mock 断言不能证明旧数据升级、文档保留及中断后的恢复。Docker 不可用使本次不能补上这一验证。
- **必要 lint 未通过（§16.5）**：三处类型 lint 错误均在已有 memory 组件测试中。
- **记忆 E2E 与在线语义评估未交付（§16.5）**：现有唯一 Playwright 测试只做会话流程且 mock 后端。没有“捕获→候选→查看具体版本→确认→新会话召回→修改→确认修订→keep/forget→晚到结果”的浏览器流程，也没有在线语义模型评估。
- **知识库文案与 D03 不一致**：`features/knowledge/knowledge-dialog.tsx:204` 仍写“历史故障经验已迁移至记忆”，规格实际决定为旧案例直接删除。

## AC 逐条复验状态

“既有通过”表示本次既有相关套件通过且审阅未发现新的明确反例；不扩大成真实服务端到端证明。“部分/未通过”表示至少一个必要分支尚不满足。

| AC | 本次状态 | 证据或限制 |
| --- | --- | --- |
| AC01 | 既有通过 | 价值门控及事实捕获测试 |
| AC02 | 既有通过 | 结果归一化与根因未确认表达 |
| AC03 | 既有通过 | 后端确认指定版本/跨会话搜索测试；具体内容审核仍见正文缺口 |
| AC04 | 既有通过 | 内容 schema 允许 claims/procedure 任一存在 |
| AC05 | **部分/未通过** | F01、F02；旧版继续召回与后端 409 已有覆盖 |
| AC06 | 既有通过 | 幂等测试、反馈唯一约束 |
| AC07 | 既有通过 | 持久 tracking 及 owner 保存路径 |
| AC08 | 既有通过 | 远端 correlation 查询/重放单测；真实 transport 跳过 |
| AC09 | 既有通过 | 模型不可用及未知结果映射；未跑真实 LLM |
| AC10 | 既有通过 | owner API/SQL/向量过滤及 trace 测试 |
| AC11 | 既有通过 | 服务/设备范围与未知范围标注测试 |
| AC12 | **部分/未通过** | F08 用户暂停被晚到事件撤销 |
| AC13 | 既有通过 | MCP 内部诊断参数契约测试 |
| AC14 | 既有通过 | 版本引用与权限说明；来源详情体验尚不完整 |
| AC15 | 既有通过 | 关键词降级及预算测试 |
| AC16 | **未通过** | F07 旧向量命中给当前无关版本加分 |
| AC17 | 既有通过 | SQL tombstone/删后召回已有测试；30 天物理清理是独立正文缺口 |
| AC18 | **未通过** | F05 多来源撤回/正文清理/修订缺失 |
| AC19 | 既有通过 | SQLite 旧表清理、新模型独立 |
| AC20 | 既有通过 | 无历史字段映射到新可信度路径 |
| AC21 | 既有通过 | 旧路由/工具/入口退役测试 |
| AC22 | 既有通过 | MQTT 退役与控制列清理已有测试 |
| AC23 | 既有通过 | 精确 source 清理测试；未跑真实外部向量库 |
| AC24 | 既有通过 | 相关后端/MCP 回归套件通过 |
| AC25 | **待验证** | SQLite 通过；MySQL 只有 mock，见验证限制 |
| AC26 | 既有通过 | 无导入/待分配入口，迁移删除遗留表 |
| AC27 | 既有通过 | keep/forget 阻止新捕获已有测试；派生清理不完整计入 AC18 |
| AC28 | 既有通过 | ACK/矛盾/未知映射测试；新增动作约束缺口计入 AC32/35 |
| AC29 | 既有通过 | 失败后的取证/诊断 context 参数测试；运行约束缺口见 AC35/36 |
| AC30 | 既有通过 | 缺新依据停止门已有测试；可核验的新依据仍主要依赖模型输出 |
| AC31 | 既有通过 | 持久化预算/三次上限/跨设备预留测试 |
| AC32 | **部分/未通过** | F03 未知结果仍允许新的同设备动作；无重复计数已有覆盖 |
| AC33 | 既有通过 | 待批预留/释放/延迟批准归属原 Run 测试 |
| AC34 | **部分/未通过** | 后端终态不重启有测试；F09 用户提示未接入 |
| AC35 | **未通过** | F03 未知未补查可新增动作；F04 期限缺执行门 |
| AC36 | **未通过** | F06 memory 异常传播阻断再诊断；预算单独保存已有覆盖 |
| AC37 | **部分/未通过** | F02 反例暂停窗口；全部召回被算作 applied |

## 重跑与证据文件

本机详细产物位于 `output/memory-acceptance-20260930/`，该目录由仓库 `.gitignore` 排除，不属于默认 CI 测试。

```powershell
# 在仓库根目录执行。只使用新的临时 SQLite；不会连接设备。
.\.tmp\memory-acceptance-20260930\venv\Scripts\python.exe output/memory-acceptance-20260930/probes.py
npm exec --workspace=packages/frontend -- vitest run --config D:/last-work/output/memory-acceptance-20260930/vitest.config.ts

# backend pytest 需在 packages/backend 工作目录执行。
D:\last-work\.tmp\memory-acceptance-20260930\venv\Scripts\python.exe -m pytest -q
```

- `probes.py` / `probe-results.json`：8 个后端边界问题的可重跑代码与最新结果。
- `ui-probes.test.tsx` / `vitest.config.ts` / `ui-probes.txt`：3 个按规格预期写的断言及失败日志；失败是验收发现，不是预期功能已通过。
- `backend-pytest.txt`：既有后端测试日志。
- `backend-environment.txt`：隔离环境依赖快照。

修复后需要将这些反例转换成正式回归测试，补齐未交付的 memory E2E、MySQL 实库及语义模型验证，再重新勾选相应 AC。不能仅把报告文字改回“全部完成”。
