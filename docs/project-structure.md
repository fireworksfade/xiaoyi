# 当前项目结构与维护入口

项目是一个 monorepo，根目录统一管理 npm workspaces、锁文件与 Docker Compose。

| 目录 | 职责 | 入口 |
| --- | --- | --- |
| `packages/frontend` | 对话、知识库、记忆与设置界面 | `app/` 路由，`features/` 业务组件，`hooks/` 状态，`lib/api/` 请求 |
| `packages/backend` | 认证、Agent 运行、审批、记忆、审计 | `app/main.py`，`app/cli.py`，`app/services/runs/` |
| `packages/mcp-services` | 设备诊断与控制、知识检索、可选模型服务 | `iot_mcp/server.py` |
| `packages/esp32-node` | ESP-IDF 设备固件、QEMU 机群镜像、Wokwi 工程 | `main/main.c`，`qemu/Dockerfile`，`wokwi.toml` |
| `packages/retrieval` | 共用 embedding 与 Qdrant HTTP 客户端 | `xiaoyi_retrieval/` |
| `deploy` | MQTT Broker 配置 | `mosquitto.conf` |
| `docs` | 当前设计与操作说明 | 本文、设备协议、架构简化说明、memory 规格 |

## 数据与配置

主后端、诊断和控制分别使用 SQLite；知识向量存于 Qdrant。历史 SQLite 与 Alembic 迁移必须保留，已有库的版本连续性和 checksum 校验依赖这些文件。

诊断与控制只运行一个 IoT MCP 服务，默认端口 9000。设备端是 QEMU 中运行的真实固件，与平台只通过 [设备协议](device-protocol.md) 约定的 MQTT 主题交互；平台代码中没有设备模拟器。

根 `.env`、各包的本地 `.env*`、运行数据库和 `data/` 属于本机状态，不随源码提交。`node_modules/` 与 `.venv/` 属于运行依赖；`output/`、`tmp/` 和 `.tmp/` 还包含个人资料、备份和验收产物，不能作为缓存统一删除。

## 构建与验证

在根目录执行 `npm ci`，前端使用 `npm run typecheck`、`npm run lint`、`npm test`、`npm run build`。

在 backend 或 mcp-services 目录执行 `python -m pip install -e ../retrieval -e ".[dev]"`，再执行 `python -m pytest`。共享检索库的独立测试位于 `packages/retrieval/tests`。

当前 IoT MCP wheel 包含 `common`、`iot_diagnosis`、`iot_control`、`iot_mcp` 和 `model_service`。旧子仓库中无法被 GitHub 发现、安装路径也已失效的嵌套 CI 配置已删除。

架构与共享配置见 [架构简化说明](architecture-simplification.md)。
