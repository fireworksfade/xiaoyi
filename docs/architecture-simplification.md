# 架构简化（2026-10-01）

保留前端、后端和统一 IoT MCP 三个应用边界。平台独立聊天是唯一的对话入口。

## 前端组件

`features/conversation` 是会话组件的唯一实现，包含消息列表、输入框、侧栏、运行记录和修复卡片。页面和测试均引用此目录。`features/settings` 管理设置，知识和记忆继续使用各自的 feature。`components/ui` 仅保存共享基础 UI；原 `components` 下的重复业务组件已删除。

迁移采用当前页面实际使用的 feature 版本，保留记忆入口和晚到修复状态展示。会话与修复卡片测试同步迁入 feature。

## 共享工具执行

`packages/backend/app/services/tool_execution.py` 的 `ToolExecutor` 负责真实诊断结果关联、可信参数准备、记忆边界、结果处理和明确失败后的再诊断。

平台 Runtime 负责 SDK 传输、模型上下文与大结果归档，并通过共享执行器以回调方式调用远端工具；工具目录权限、调用去重、取消、审计和事件持久化继续由运行编排与既有业务模块负责，不创建第二个运行或启动模型。

自动再诊断继续走专用回调：执行前检查只读工具策略。审批、每轮修复预算、记忆版本与采用检查继续由已有业务模块实施。远端写入不新增自动重试。

## 共享检索基础库

`packages/retrieval/xiaoyi_retrieval` 是无运行时第三方依赖的小型 Python 包，统一同步/异步 JSON 请求、embedding 请求和响应校验、地址规范化、Qdrant 查询/集合请求构造。异步 HTTP 客户端由后端传入并负责生命周期和超时；同步客户端保持原 urllib 传输与超时。

知识库保留 hash/远程模型 provider、查询指令、BM25、融合、重排和主/兜底集合路由。记忆保留用户过滤、版本/模型指纹检查、删除保护和独立 outbox。共享客户端不会读取业务数据库或决定记忆是否有效。

共享环境变量：

| 配置 | 含义 |
| --- | --- |
| `RETRIEVAL_QDRANT_URL` | Qdrant 服务地址 |
| `RETRIEVAL_EMBEDDING_BASE_URL` | embedding 服务根地址或 `/v1` 基地址 |
| `RETRIEVAL_EMBEDDING_MODEL` | embedding 模型 |
| `RETRIEVAL_EMBEDDING_API_KEY` | 可选 API Key；知识库远程 provider 仍要求非空 |
| `RETRIEVAL_EMBEDDING_DIMENSIONS` | 向量维度 |

对应的 `MEMORY_*` / `DIAGNOSIS_*` 专用变量优先。使用共享配置时，应移除 `.env` 中对应的专用默认值；后端显式空的 `MEMORY_EMBEDDING_URL` 或 `MEMORY_QDRANT_URL` 仍可禁用记忆向量检索。修改模型时也需更新 `MEMORY_EMBEDDING_FINGERPRINT` 并重建相应索引，不得复用旧模型指纹。

默认 Portable 配置保持 hash 知识检索与 SQL 记忆检索。Compose 的检索模型覆盖文件继续启用知识库远程 provider；同时使用记忆向量时，在根 `.env` 显式设置：

```dotenv
RETRIEVAL_QDRANT_URL=http://qdrant:6333
RETRIEVAL_EMBEDDING_BASE_URL=http://retrieval-models:9010/v1
RETRIEVAL_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
RETRIEVAL_EMBEDDING_API_KEY=local-model-service
RETRIEVAL_EMBEDDING_DIMENSIONS=512
```

宿主机运行时把服务名换成 `127.0.0.1` 和对应端口。知识库和记忆数据始终使用各自的集合。

## 安装与更新

在 `packages/backend` 或 `packages/mcp-services` 下执行：

```bash
python -m pip install -e ../retrieval -e ".[dev]"
python -m pytest
```

独立验证共享库时，在 `packages/retrieval` 下执行 `python -m pip install -e ".[dev]"` 和 `python -m pytest`。

Compose 使用 `additional_contexts` 引入共享源码，无须扩大整个仓库的构建上下文。首次应用此次改动需要重建镜像：

```bash
docker compose up -d --build backend iot-mcp iot-simulator-fleet
```

使用检索模型档位时继续带原有 `-f` 覆盖文件。后续共享库源码变更可通过开发 Compose 中的只读挂载与服务重启加载。依赖或元数据变化仍需重建。

直接构建镜像时，在仓库根目录执行：

```bash
docker build --build-context retrieval=packages/retrieval -f packages/backend/Dockerfile packages/backend
docker build --build-context retrieval=packages/retrieval -f packages/mcp-services/Dockerfile packages/mcp-services
```

此改动不新增业务表或数据库迁移。

## 验证

2026-10-01 验证结果：

| 检查 | 结果 |
| --- | --- |
| 前端类型检查、lint、生产构建 | 通过 |
| 前端 Vitest | 37 passed |
| 平台后端完整回归 | 160 passed、1 skipped；新增配置覆盖测试另有 2 passed |
| IoT MCP 完整回归 | 155 passed、5 skipped；新增配置覆盖与 Portable 维度保护测试另有 2 passed，相关降级回归 16 passed |
| 共享检索库 | 10 passed，含同步/异步请求一致性、异常向量拒绝与过滤条件保留 |
| 普通会话浏览器流程 | 1 passed；未启用的独立记忆流程跳过 |
| 隔离后端＋前端代理的记忆浏览器联调 | 2 passed，覆盖会话和真实记忆 worker 流程 |
| 修改文件的 Ruff 和前端格式检查 | 通过 |
| Compose 基础/检索/离线配置校验 | 通过 |
| MCP 新镜像构建与共享库导入 | 通过 |
| 后端新镜像构建 | 未完成：pip 依赖下载缓慢，耗时超过 12 分钟后停止此项附加验证；后端完整回归已用已有镜像及最终源码挂载验证 |

后端测试使用隔离容器，源代码只读挂载，测试数据库为临时数据库；记忆浏览器后端也使用一次性 SQLite 数据库，未启动或修改现有业务服务。Windows 后端本地虚拟环境存在 Python 3.14 解释器与 cp312 扩展不匹配，未改动该环境的原有依赖。

全库 `npm run format:check` 仍报告 44 个未改文件的既有格式问题，本次修改/迁移的前端文件单独检查通过。

## 重启记录（2026-10-01）

用户授权重启后，已基于正在运行的后端镜像构建增量镜像，安装本地构建的后端与共享检索 wheel 并更新应用源码。已核对既有依赖版本满足项目声明，`pip check` 通过；回退镜像保留为 `last-work-backend:before-architecture-20261001`。这次增量构建不依赖重新下载运行时依赖，原始 Dockerfile 的全量下载构建记录仍如上所述。

按实际正在使用的基础 Compose/Portable 配置重建并启动 backend、iot-mcp 和 iot-simulator-fleet 容器，新增共享源码挂载已应用；既有环境变量核对无变化。前端已在 `127.0.0.1:3000` 启动。

验证结果：后端与 MCP `/ready` 均就绪，前端页面返回 200，同源 `/api/backend/ready` 返回后端 ready，两端共享检索包均为 0.1.0。此次更新未重建或清除持久化数据卷。
