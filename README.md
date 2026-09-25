# Xiaoyi IoT 平台

基于智能体和 MCP 的 IoT 设备诊断与控制平台。前端提供对话、知识文档和管理界面；FastAPI 后端负责认证、对话、Agent 运行与工具策略；统一 IoT MCP 服务提供设备诊断、知识检索和设备控制能力。

## 当前架构

| 组件 | 目录或服务 | 职责 |
| --- | --- | --- |
| 前端 | `packages/frontend` | React 19 + Vinext，浏览器通过同源 `/api/backend` 代理访问后端 |
| 后端 | `packages/backend` | FastAPI、SQLite、Agent 运行、SSE、MCP 工具目录与审批策略 |
| IoT MCP | `packages/mcp-services/iot_mcp` | 单个 Streamable HTTP 服务，整合诊断与控制工具 |
| 基础设施 | `compose.yaml` | MQTT、Qdrant、Jaeger、设备模拟机群及后端和 MCP 容器 |

默认 Compose 使用本地 hash embedding 和 weighted reranker，无需 GPU 或模型下载。后端默认使用演示 Runtime；若数据库中已保存模型配置，运行时会使用该配置。

## 快速开始

需要 Docker Compose 和 Node.js 22.13 或更高版本。基础 Compose **不启动前端**，因此按下面两步分别启动。

### 1. 启动后端与 IoT MCP

在仓库根目录运行：

```bash
docker compose up -d --build
docker compose ps
docker compose exec -T backend python scripts/bootstrap_local_mcp.py
```

最后一条命令向后端注册 `http://iot-mcp:9000/mcp`，测试连接、刷新工具目录并配置风险策略。重复运行可刷新已有连接。开发环境使用演示账号 `admin / admin123`；该账号只适用于本地开发。

### 2. 启动前端

另开一个终端：

```bash
cd packages/frontend
npm ci
npm run dev -- --hostname 127.0.0.1
```

打开 [前端](http://127.0.0.1:3000)。本地前端默认把 `/api/backend` 请求代理到 `http://127.0.0.1:8000`；需要更改后端地址时，在 `packages/frontend/.env.local` 中设置 `BACKEND_BASE_URL`。`--hostname` 是 Vinext 使用的绑定参数。

### 服务地址与检查

| 地址 | 用途 |
| --- | --- |
| [127.0.0.1:3000](http://127.0.0.1:3000) | 前端（单独启动） |
| [127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) | 后端 API 文档 |
| [127.0.0.1:8000/ready](http://127.0.0.1:8000/ready) | 后端业务就绪检查 |
| [127.0.0.1:9000/ready](http://127.0.0.1:9000/ready) | IoT MCP 就绪检查 |
| [127.0.0.1:16686](http://127.0.0.1:16686) | Jaeger 追踪界面 |
| [127.0.0.1:6333/dashboard](http://127.0.0.1:6333/dashboard) | Qdrant 管理界面 |

MCP 服务连接成功后，前端“设置 → MCP 服务”中可查看服务及工具。注册脚本将查询与诊断工具设为只读策略、可发起的动作设为提案策略、需人工审批的写入与删除工具设为审批策略；未列入策略的工具保持禁用。

## 配置

- 后端本地运行配置参见 [`packages/backend/.env.example`](packages/backend/.env.example)。`AGENT_RUNTIME=mock` 可用于无模型密钥的联调；使用真实模型时配置模型 API 或相应环境变量。
- IoT MCP 的 Compose 环境变量位于 [`compose.yaml`](compose.yaml)。`DIAGNOSIS_LLM_API_KEY` 为可选项；默认 Portable 检索不依赖外部模型。
- 当前 `compose.yaml` 使用开发密钥、演示账号和本地端口绑定。生产部署须另行配置密钥、账号、数据库和 Cookie 策略，参见 [`packages/backend/README.md`](packages/backend/README.md)。
- `compose.retrieval-gpu.yaml` 目前仍引用旧服务名 `iot-diagnosis-mcp` 与旧路径 `./mcp-services`，**不能直接与当前基础 Compose 叠加使用**；`compose.retrieval-offline.yaml` 依赖该 GPU 配置。基础流程请使用上面的 Portable 命令。

## 测试

前端命令在 `packages/frontend` 中执行：

```bash
npm run typecheck
npm run lint
npm test
npx playwright install chromium  # 首次运行端到端测试时安装浏览器
npm run test:e2e
```

后端与 MCP 服务分别在对应目录安装开发依赖后运行：

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

前端测试使用 Vitest 和 Playwright；后端与 MCP 服务测试使用 pytest。Python 需要 3.12 或更高版本。

## 常用维护命令

```bash
docker compose logs -f backend iot-mcp
docker compose down
```

`docker compose down` 保留命名数据卷。后端迁移与就绪检查、运行事件和数据保留机制详见 [`packages/backend/README.md`](packages/backend/README.md)。
