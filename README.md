# Xiaoyi IoT 平台

> 基于智能体和 MCP 协议的 IoT 设备诊断与控制平台

## 项目概述

Xiaoyi 是一个现代化的 IoT 平台，通过 AI 智能体技术提供设备故障诊断和远程控制能力。平台采用 Monorepo 架构，集成了前端交互界面、智能体后端服务和 MCP（Model Context Protocol）服务。

### 核心特性

- **智能诊断**：基于 RAG（检索增强生成）的设备故障诊断，支持多种检索策略
- **远程控制**：通过 MQTT 协议实现设备控制指令的安全下发与验证
- **会话管理**：支持多轮对话的智能体交互，包含上下文恢复和工具审批机制
- **知识库**：文档管理、故障案例库，支持 PDF 文档解析与向量检索
- **可观测性**：集成 OpenTelemetry 和 Jaeger 进行分布式追踪
- **模块化架构**：前后端分离，MCP 服务独立部署

## 技术栈

### 前端 (packages/frontend)
- **框架**: React 19 + Vinext (基于 Vite 的 SSR 框架)
- **UI 组件**: shadcn/ui + Base UI
- **样式**: Tailwind CSS 4.2
- **类型检查**: TypeScript 5.9
- **测试**: Vitest + Playwright
- **部署**: Cloudflare Workers

### 后端 (packages/backend)
- **框架**: FastAPI 0.141
- **AI SDK**: OpenAI Agents 0.22
- **数据库**: SQLite + SQLAlchemy 2.0 + Alembic
- **可观测性**: OpenTelemetry + Prometheus
- **异步运行时**: Uvicorn + asyncio

### MCP 服务 (packages/mcp-services)
- **协议**: MCP 2.1.1
- **设备通信**: MQTT (Paho) + Eclipse Mosquitto
- **向量数据库**: Qdrant 1.19
- **Embedding**: 支持 Hash/GPU 模式（可配置）
- **重排序**: Weighted reranker / GPU reranker

## 快速开始

### 环境要求

- **Node.js**: >= 22.13.0
- **Python**: >= 3.12
- **pnpm**: >= 8.0.0
- **Docker**: 20.10+ (用于 Compose 部署)

### 本地开发

#### 1. 使用 Docker Compose（推荐）

```bash
# 启动所有服务（无 GPU 模式）
docker compose up -d --build

# GPU 检索模式（需要 NVIDIA GPU）
docker compose -f compose.yaml -f compose.retrieval-gpu.yaml up -d --build

# 离线缓存模式
docker compose -f compose.yaml -f compose.retrieval-gpu.yaml -f compose.retrieval-offline.yaml up -d --build
```

服务地址：
- 前端: http://localhost:3000
- 后端 API: http://localhost:8000
- IoT MCP 服务: http://localhost:9000
- Jaeger UI: http://localhost:16686
- Qdrant UI: http://localhost:6333/dashboard

#### 2. 手动开发模式

**前端开发**:
```bash
cd packages/frontend
pnpm install
pnpm dev
```

**后端开发**:
```bash
cd packages/backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m app.cli deploy   # 初始化数据库
uvicorn app.main:app --reload
```

**MCP 服务**:
```bash
cd packages/mcp-services
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m scripts.migrate upgrade --service diagnosis
python -m scripts.migrate upgrade --service control
python -m iot_mcp.server
```

### 环境变量配置

复制 `.env.example` 为 `.env`（如果存在），或参考 `compose.yaml` 中的环境变量配置：

**必需配置**:
- `DIAGNOSIS_LLM_API_KEY`: LLM API 密钥
- `DIAGNOSIS_LLM_BASE_URL`: LLM API 地址（默认 OpenAI）
- `DIAGNOSIS_LLM_MODEL`: 使用的模型名称

**可选配置**:
- `RAG_CHUNK_SIZE`: 文档分块大小（默认 512）
- `RAG_RETRIEVAL_STRATEGY`: 检索策略 (hybrid/dense/sparse)
- `DIAGNOSIS_EMBEDDING_PROVIDER`: Embedding 提供商 (hash/gpu)

## 项目结构

```
.
├── packages/
│   ├── backend/              # FastAPI 后端服务
│   │   ├── app/
│   │   │   ├── agent/       # 智能体运行时与工具语义
│   │   │   ├── api/         # REST API 路由
│   │   │   ├── services/    # 业务逻辑层
│   │   │   ├── models.py    # SQLAlchemy 模型
│   │   │   └── main.py      # 应用入口
│   │   ├── migrations/      # Alembic 数据库迁移
│   │   └── tests/           # 后端测试
│   │
│   ├── frontend/            # React 前端应用
│   │   ├── app/            # 路由与页面
│   │   ├── components/     # React 组件
│   │   ├── lib/            # 工具函数与 API 客户端
│   │   └── test/           # 前端测试
│   │
│   └── mcp-services/       # MCP 协议服务
│       ├── iot_diagnosis/  # 诊断服务（RAG + 检索）
│       ├── iot_control/    # 控制服务（MQTT + 指令）
│       ├── iot_mcp/        # MCP 服务器
│       ├── common/         # 共享工具
│       └── evals/          # 评估与测试用例
│
├── docs/                   # 项目文档
├── deploy/                 # 部署配置
├── scripts/                # 工具脚本
└── compose.yaml            # Docker Compose 配置
```

详细架构说明见 [docs/project-structure.md](docs/project-structure.md)

## 测试

### 前端测试
```bash
pnpm test          # 单元测试
pnpm test:e2e      # E2E 测试
pnpm typecheck     # 类型检查
pnpm lint          # 代码检查
```

### 后端测试
```bash
cd packages/backend
pytest                    # 运行所有测试
pytest tests/api/         # 测试 API 层
mypy app                  # 类型检查
ruff check app            # 代码检查
```

### MCP 服务测试
```bash
cd packages/mcp-services
pytest                    # 运行所有测试
pytest tests/diagnosis/   # 诊断服务测试
mypy iot_diagnosis        # 类型检查
```

## API 文档

启动后端服务后访问：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## 部署

### Docker 部署

生产环境建议使用 Docker Compose：

```bash
# 构建并启动所有服务
docker compose up -d --build

# 查看日志
docker compose logs -f

# 停止服务
docker compose down

# 清理数据卷（谨慎操作）
docker compose down -v
```

### 健康检查

- 后端: `GET http://localhost:8000/health`
- IoT MCP: `GET http://localhost:9000/ready`

## 开发指南

### 代码风格

- **Python**: 使用 Ruff 进行格式化和检查（最大行长 100）
- **TypeScript**: 使用 oxlint + oxfmt
- **提交信息**: 遵循 Conventional Commits 规范

### 添加新功能

1. 在对应的 package 中创建功能分支
2. 编写测试用例
3. 实现功能代码
4. 运行完整的测试套件和类型检查
5. 提交 PR 并通过 CI 检查

### 数据库迁移

```bash
# 后端
cd packages/backend
alembic revision --autogenerate -m "描述"
alembic upgrade head

# MCP 服务（诊断）
cd packages/mcp-services
python -m scripts.migrate create --service diagnosis --message "描述"
python -m scripts.migrate upgrade --service diagnosis

# MCP 服务（控制）
python -m scripts.migrate create --service control --message "描述"
python -m scripts.migrate upgrade --service control
```

## 监控与调试

### 分布式追踪
访问 Jaeger UI (http://localhost:16686) 查看请求追踪：
- 服务: `xiaoyi-backend`, `xiaoyi-iot-mcp`
- 支持跨服务调用链分析

### 向量数据库管理
访问 Qdrant Dashboard (http://localhost:6333/dashboard) 管理向量集合

### 日志查看
```bash
# 查看特定服务日志
docker compose logs -f backend
docker compose logs -f iot-mcp

# 查看所有日志
docker compose logs -f
```

## 常见问题

### 1. 前端无法连接后端
- 检查 `FRONTEND_ORIGINS` 环境变量是否包含前端地址
- 确认 CORS 配置正确

### 2. IoT 设备连接失败
- 检查 MQTT broker 是否正常运行
- 验证设备配置中的 MQTT 地址和端口

### 3. RAG 检索结果不准确
- 调整 `RAG_CHUNK_SIZE` 和 `RAG_CHUNK_OVERLAP`
- 尝试不同的 `RAG_RETRIEVAL_STRATEGY`
- 检查 Qdrant 中的向量数据是否正确同步

### 4. 数据库迁移失败
- 检查数据库文件权限
- 确认所有迁移脚本按顺序执行
- 查看迁移日志中的详细错误信息

## 贡献指南

欢迎贡献代码、报告问题或提出建议！

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启 Pull Request

## 许可证

[待定]

## 联系方式

项目维护者: yijia

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
