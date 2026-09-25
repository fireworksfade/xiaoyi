# P1 架构优化计划

## 目标
在 P0 优化（容器精简）基础上，提升系统可观测性、可靠性和性能。

## Stage 4: 核心改进

### 4.1 OpenTelemetry 可观测性
**目标**: 统一的分布式追踪和指标收集

**实现**:
1. **基础设施**
   - 添加 Jaeger all-in-one 容器（开发环境）
   - 配置 OTLP exporter
   - 端口：16686 (UI), 4318 (OTLP HTTP)

2. **后端集成** (packages/backend)
   - 安装 `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`
   - 自动追踪所有 HTTP 请求
   - 手动 span: Agent 循环、MCP 调用、数据库操作

3. **MCP 服务集成** (packages/mcp-services)
   - 安装 `opentelemetry-api`, `opentelemetry-sdk`
   - 追踪工具调用：诊断、检索、控制命令
   - 上下文传播：从后端 → MCP → MQTT

4. **关键指标**
   - 请求延迟 (p50, p95, p99)
   - 工具调用成功率
   - 诊断检索准确率
   - MQTT 消息延迟

**验证**:
```bash
# 访问 Jaeger UI
http://localhost:16686

# 查看追踪：对话 → Agent → MCP 工具 → MQTT 设备
```

### 4.2 增强错误处理
**目标**: 统一的错误处理和重试策略

**实现**:
1. **MCP 工具错误分类**
   ```python
   # common/errors.py
   class MCPError(Exception):
       retryable: bool
       error_code: str
   
   class TransientError(MCPError):
       retryable = True
   
   class PermanentError(MCPError):
       retryable = False
   ```

2. **自动重试装饰器**
   ```python
   @retry_on_transient(max_attempts=3, backoff=exponential)
   async def call_mcp_tool(...):
       ...
   ```

3. **错误聚合**
   - 后端收集 MCP 错误统计
   - 按工具、错误码分组
   - 暴露 `/api/admin/errors` 端点

### 4.3 简化状态管理
**目标**: 减少数据库写入，优化并发控制

**实现**:
1. **诊断服务状态优化**
   - 当前：每次 MQTT 消息写数据库
   - 优化：内存缓存 + 批量写入（每 10 秒或 100 条）
   - 保留：故障事件立即写入

2. **控制服务状态简化**
   - 移除冗余的 `command_sent_at` / `command_delivered_at`
   - 统一使用 `updated_at` + `status` 枚举
   - 验证窗口：从提案批准时间开始计算

3. **并发控制**
   - 诊断：乐观锁（version 字段）
   - 控制：悲观锁（SELECT FOR UPDATE）仅用于提案决策

### 4.4 性能监控
**目标**: 主动发现性能瓶颈

**实现**:
1. **慢查询日志**
   ```python
   # 自动记录 > 100ms 的数据库查询
   @log_slow_queries(threshold_ms=100)
   async def query(...):
       ...
   ```

2. **资源使用监控**
   - 添加 `/metrics` 端点（Prometheus 格式）
   - 指标：CPU、内存、数据库连接池、MQTT 队列深度

3. **性能基准**
   ```python
   # packages/mcp-services/evals/perf_benchmark.py
   - 诊断检索: < 200ms (p95)
   - 工具调用: < 500ms (p95)
   - 端到端对话: < 2s (p95)
   ```

## 实施顺序
1. ✅ Stage 1: MySQL 镜像层移除
2. ✅ Stage 2: 统一 MCP 服务器
3. ✅ Stage 3: Monorepo 转换
4. ⏳ Stage 4.1: OpenTelemetry (1-2 天)
5. ⏳ Stage 4.2: 错误处理 (1 天)
6. ⏳ Stage 4.3: 状态管理 (1 天)
7. ⏳ Stage 4.4: 性能监控 (1 天)

## 依赖变更
```diff
# packages/backend/requirements.txt
+opentelemetry-api==1.29.0
+opentelemetry-sdk==1.29.0
+opentelemetry-instrumentation-fastapi==0.50b0
+opentelemetry-exporter-otlp==1.29.0

# packages/mcp-services/requirements.txt
+opentelemetry-api==1.29.0
+opentelemetry-sdk==1.29.0
+opentelemetry-exporter-otlp==1.29.0
```

## 容器变更
```yaml
# compose.yaml - 添加 Jaeger
services:
  jaeger:
    image: jaegertracing/all-in-one:2.3.1
    ports:
      - "127.0.0.1:16686:16686"  # UI
      - "127.0.0.1:4318:4318"    # OTLP HTTP
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
```

## 回滚策略
- OpenTelemetry 可通过环境变量禁用：`OTEL_SDK_DISABLED=true`
- 错误处理向后兼容现有 API
- 状态管理迁移脚本：`scripts/migrate_state_schema.py`
