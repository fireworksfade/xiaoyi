# 项目清理与结构优化建议

## 本次清理（2026-09-24）

- 根据 TypeScript 语法树中的本地模块引用，从业务代码、路由、测试与配置递归追踪依赖，删除不可达的 48 个模板 UI 组件及 `hooks/use-mobile.ts`。
- `frontend/components/ui/` 保留 11 个实际使用的基础组件：badge、button、dialog、dropdown-menu、input、label、select、sheet、switch、tabs、textarea。
- 移除仅服务于被删组件或未被源码使用的 7 项直接依赖：`@shadcn/react`、`cmdk`、`date-fns`、`embla-carousel-react`、`input-otp`、`react-day-picker`、`react-resizable-panels`，同步更新 npm 锁文件。某些包仍可能作为其他工具的传递依赖出现。
- 补充 `.mypy_cache/`、`.ruff_cache/` 的 Git 忽略规则。

`.tmp/` 中的验收结果、`tmp/` 和 `output/` 中的个人文档与素材均保留；它们不是可确认无用的缓存。数据库、本地环境变量、迁移、测试、工作记录和设计规格也保留。`mcp-services/` 是独立 Git 仓库，本次没有修改其内容。

验证结果：前端 lint、格式检查、类型检查、28 项单元测试、1 项 Playwright 端到端测试和生产构建全部通过。锁文件移除 35 个包条目，保留包的版本与完整性校验值未变。后端代码未改动，本次未重跑后端测试。

后端缓存批量删除命令被自动审批策略阻止，未执行；`.mypy_cache/`、`.ruff_cache/`、`.pytest_cache/` 和 Python 字节码缓存仍保留。

## 建议按以下顺序优化

### 1. 前端按业务组织，优先拆分大组件

`settings-sheet.tsx` 和 `knowledge-dialog.tsx` 各有数百行，包含多个功能；`lib/api.ts` 集中了不同业务的请求与类型。下一步建议：

- 将设置中的模型配置、MCP 服务管理拆成独立组件，保留一个薄的面板入口。
- 将知识库的文档管理、检索、故障案例分别组织为组件及对应 Hook。
- 将 API 客户端拆成共用请求层及 auth、conversations、runs、knowledge、mcp 模块；共用层统一处理 Cookie、CSRF、错误解析。
- 业务组件和 Hook 放在同一个 feature 中，测试随模块放置；`components/ui/` 只保留跨业务复用的基础组件。

建议目标结构（尚未执行迁移）：

```text
frontend/
├── app/                       # 路由、布局、后端代理
├── features/
│   ├── conversation/          # 会话界面、消息与运行 Hook、测试
│   ├── knowledge/             # 文档、检索、案例
│   ├── settings/              # 模型与 MCP 配置
│   └── remediation/           # 审批卡片与测试
├── components/ui/             # 共享基础组件
├── lib/
│   ├── api/                   # 请求基础设施与各业务 API
│   ├── datetime.ts
│   └── utils.ts
├── test/                      # 全局测试初始化、通用测试工具
└── e2e/                       # 跨功能端到端流程
```

### 2. 后端先明确运行模块边界，再考虑目录分组

`app/services/runs.py` 同时协调事件、上下文恢复、工具提案和 Completion Gate。建议逐步抽出有独立职责的代码，保持 `execute_claimed_run` 为清晰的编排入口。现有 dispatcher、recovery、state、event_buffer 已经分离，应优先复用这些边界，避免新建重复服务。

运行相关模块较多，可在后续独立重构中归入 `services/runs/` 包；迁移时保留现有导入接口，重点验证取消、恢复、SSE、审批与事务边界。`models.py` 和 `schemas.py` 暂时仍可管理，无须为了目录对称立即拆分。历史数据库迁移必须保留。

### 3. 区分稳定文档、工作记录和个人产物

- README 保留启动步骤与导航，稳定的架构和部署说明逐步放入 `docs/`。
- 当前根目录 `WORK_STATE.md` 已较长，建议按月份归档到 `docs/history/`，根文件只保留当前状态和链接；归档前核对旧记录中的相对路径。
- `specs/` 保留需求与验收依据，修正 README 中只描述 RAG/IoT MCP 的旧说明。
- 个人简历与面试资料建议另行迁出项目；当前继续忽略，避免随源码提交。验收数据确认已归档后再清理。

### 4. 保持两个仓库的部署边界

`mcp-services/` 被主仓库忽略，却由根 Compose 构建使用。建议在发布说明中记录主仓库与 MCP 仓库验证通过的提交 SHA，减少各自更新造成的组合差异；如以后采用 submodule，应单独迁移并更新 CI 和克隆说明。

根目录 Compose 文件目前承担统一入口，路径与 build context 有实际依赖，暂不搬动。`frontend/.openai/hosting.json`、`vite.config.ts` 和 `next.config.ts` 属于当前构建配置，不能仅因名称看似模板文件而删除。

### 5. 后续清理以引用和验证为准

新增 UI 组件按需引入；删除组件后检查独占依赖并同步锁文件。目录迁移分批进行，每批运行 lint、格式检查、类型检查、相关单元测试、E2E 和构建。缓存目录可重新生成；验收证据、用户文件、运行数据不能只凭目录名判断为垃圾。
