# 全项目清理记录（2026-10-01）

## 审查范围

审查前端、主后端、统一 IoT MCP、共享检索库、Compose、维护脚本、依赖声明、文档和本机生成目录。使用 Python 语法树、TypeScript 模块解析与全库引用搜索区分实际调用、框架入口、类型引用、CSS 依赖和历史升级需求。

## 已删除与收敛

- MySQL 的依赖、示例配置、迁移框架与迁移文件、实库验收和已跳过的镜像重建测试；删除调用失效接口的旧重建 CLI。历史验收报告保留当时证据，并明确标注当前不再支持 MySQL。
- 前端知识库类型与测试中的 `mysql_saved` 字段；实际接口已经不返回该字段。
- 同名包已取代的 `iot_diagnosis/external.py` 和 `simulator.py`；实际 `external/`、`simulator/` 包及命令入口保留。
- 未引用的公共时间模块、旧控制服务独立认证模块、双服务 HTTP 诊断验证客户端及其两项旧测试；统一 MCP 的动作 schema 验证迁入 `test_control_tool_schemas.py`。
- 未引用的旧诊断服务冒烟脚本，三个无调用的前端 feature 聚合导出文件，以及五份直接登录或操作本地数据库的一次性后端调试脚本。
- 主后端未调用的知识服务选择/审批辅助函数、分页包装函数、五个响应类型、恢复任务列表辅助函数、进度更新辅助函数、token Protocol；保留实际运行路径与具体估算器。
- 未调用的分块兼容入口、模型健康探测函数及对应环境变量；保留模型服务本身的 `/ready`、缓存验证和实际检索降级。
- 未使用的能力集合、参数类型集合、分块类型集合和终态集合。
- 旧双服务的 9001/9002 监听、认证和验证配置，统一使用 `IOT_MCP_HOST` / `IOT_MCP_PORT` 与实际生效的诊断令牌配置。
- 无法在 monorepo 根目录生效、安装路径已失效的嵌套 GitHub workflow；旧 P1 计划中的实现建议已不匹配当前架构，删除该计划并重写当前项目结构说明。
- 已不存在的独立仓库忽略规则、调试脚本专用忽略规则。

## 修复的接口接线

- MCP 创建了认证配置但未传入 `MCPServer`。现已接入 `auth` 和 `token_verifier`：未配置令牌时保持本地开放模式；配置后无令牌和错误令牌请求返回 401，正确令牌可以初始化 MCP，会话健康检查仍可访问。
- 定时保留任务传入 Repository 并调用已不存在的 `execute`。改为传入数据库路径并调用 `run`；默认仍为 dry-run，不自动开启数据删除。
- MCP wheel 的包列表遗漏统一服务 `iot_mcp`。现已纳入安装包，避免只在源码工作目录下才能导入该入口。

## 保留范围

实际使用的 UI 组件、CSS 与构建依赖、平台聊天、模拟器、知识文档、检索模型与离线档位均保留。SQLite 与 Alembic 历史迁移保持原样，避免破坏已有库升级或 checksum 校验。

未更改运行数据库、密钥、用户资料、安装包、备份或既有验收产物。`.archify` 中 README 引用的图和验证依据保留。`node_modules`、`.venv` 仍用于运行；`output`、`tmp`、`.tmp` 含个人产物与历史验证数据，未当作缓存删除。

缓存目录约 195 MiB，另有约 0.4 MiB 的旧 Python build 与前端 `.next` 目录。批量删除这些目录的命令被自动审批策略拒绝，工具只返回 `blocked by policy`，因此目录仍保留；删除源码文件的逐文件编辑已成功执行。

## 验证

| 检查 | 结果 |
| --- | --- |
| 后端全量 pytest | 162 passed、1 skipped；最终恢复/能力路由检查另有 10 passed |
| MCP 全量 pytest | 154 passed；最终动作/分块/生命周期/schema 检查另有 31 passed |
| 共享检索库 | 10 passed |
| 前端 Vitest | 37 passed |
| 浏览器完整会话与真实记忆 worker 流程 | 2 passed，使用一次性后端及数据库 |
| 前端类型检查、lint、生产构建 | 通过 |
| Python 全应用、维护脚本和测试 Ruff | 通过 |
| 新增测试格式检查、Git whitespace 检查 | 通过 |
| 基础 Compose + 检索模型 + 离线覆盖配置 | config --quiet 通过 |
| MCP wheel 构建与内容核验 | 通过，包含统一服务和实际包入口，无已退役文件与 MySQL 依赖 |

本机 backend 虚拟环境存在扩展兼容问题，使用系统 Python 3.14 和显式 `PYTHONPATH=packages/retrieval` 进行后端验证，未更改该虚拟环境。浏览器联调用同一路径连接临时服务，不访问现有业务数据库。

清理验证阶段 Docker daemon 不可用，当时未重建或重启业务容器。后续已完成镜像更新与服务重启，见下一节。

## 清理后的重启（2026-10-01 16:36，Asia/Shanghai）

用户授权重启后，启动 Docker Desktop 并恢复原有数据卷。确认实际配置为 Portable（hash 384 维、weighted reranker），后端未启用共享远程 embedding。

基于已有 MCP 镜像构建增量镜像，安装本次最终源码的 wheel 与依赖声明，卸载 PyMySQL 并清除镜像中已退役的模块；`pip check` 通过。回退镜像为 `last-work-iot-mcp:before-cleanup-20261001`。模拟器复用同一个新镜像。后端、IoT MCP 和模拟器容器已按现有 Compose 重建启动，源码挂载生效；前端以隐藏进程启动于 127.0.0.1:3000。

Docker 自动恢复了旧 MySQL 和可选模型容器。旧 MySQL 已停止并关闭自动重启；当前 Portable 档位与后端不使用模型服务，该容器也已停止并关闭自动重启。保留容器、数据库数据卷和模型缓存；以后显式启用检索模型档位时，可通过原 Compose 覆盖文件重新启动。

前端页面、主后端 `/ready`、IoT MCP `/ready` 和前端同源代理 `/api/backend/ready` 均返回 200。后端数据库、schema 与 dispatcher 均就绪；诊断/控制迁移无 pending，Qdrant 已连接，12 台模拟设备上线。容器内核对已无 PyMySQL 模块，MCP 安装依赖声明已更新。本次未清除或重建任何持久化数据卷。
