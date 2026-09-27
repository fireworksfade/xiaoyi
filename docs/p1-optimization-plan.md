# P1 架构优化计划

## 目标
在 P0 优化（容器精简）基础上，提升系统可靠性和性能。

## Stage 4: 核心改进

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
4. ⏳ Stage 4.2: 错误处理 (1 天)
5. ⏳ Stage 4.3: 状态管理 (1 天)
6. ⏳ Stage 4.4: 性能监控 (1 天)

## 回滚策略
- 错误处理向后兼容现有 API
- 状态管理迁移脚本：`scripts/migrate_state_schema.py`
