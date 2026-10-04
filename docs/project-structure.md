# 当前项目结构与维护入口

项目是一个 monorepo，根目录统一管理 npm workspaces、锁文件与 Docker Compose。

| 目录 | 职责 | 入口 |
| --- | --- | --- |
| `packages/frontend` | 对话、知识库、记忆与设置界面 | `app/` 路由，`features/` 业务组件，`hooks/` 状态，`lib/api/` 请求 |
| `packages/backend` | 认证、Agent 运行、审批、记忆、审计 | `app/main.py`，`app/cli.py`，`app/services/runs/` |
| `packages/mcp-services` | 设备诊断与控制、知识检索、模拟器、可选模型服务 | `iot_mcp/server.py`，`iot_diagnosis/simulator/__main__.py` |
| `packages/retrieval` | 共用 embedding 与 Qdrant HTTP 客户端 | `xiaoyi_retrieval/` |
| `deploy` | MQTT Broker 配置 | `mosquitto.conf` |
| `docs` | 当前设计、操作说明和注明日期的验收记录 | 本文、架构简化说明、memory 规格及验收报告 |

## 数据与配置

主后端、诊断和控制分别使用 SQLite；知识向量存于 Qdrant。历史 SQLite 与 Alembic 迁移必须保留，已有库的版本连续性和 checksum 校验依赖这些文件。

诊断与控制只运行一个 IoT MCP 服务，默认端口 9000。`external/` 和 `simulator/` 是实际实现；已删除同名 `.py` 兼容文件，原包导入和 `python -m iot_diagnosis.simulator` 命令仍可使用。

根 `.env`、各包的本地 `.env*`、运行数据库和 `data/` 属于本机状态，不随源码提交。`node_modules/` 与 `.venv/` 属于运行依赖；`output/`、`tmp/` 和 `.tmp/` 还包含个人资料、备份和验收产物，不能作为缓存统一删除。

## 构建与验证

在根目录执行 `npm ci`，前端使用 `npm run typecheck`、`npm run lint`、`npm test`、`npm run build`。

在 backend 或 mcp-services 目录执行 `python -m pip install -e ../retrieval -e ".[dev]"`，再执行 `python -m pytest`。共享检索库的独立测试位于 `packages/retrieval/tests`。

当前 IoT MCP wheel 包含 `common`、`iot_diagnosis`、`iot_control`、`iot_mcp` 和 `model_service`。旧子仓库中无法被 GitHub 发现、安装路径也已失效的嵌套 CI 配置已删除。

2026-10-01 全项目清理范围与验证记录见 [清理记录](project-cleanup-20261001.md)。架构与共享配置见 [架构简化说明](architecture-simplification.md)。
