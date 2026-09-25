#!/bin/bash
# OpenTelemetry 集成快速验证脚本

set -e

echo "=== OpenTelemetry 集成验证 ==="
echo

# 1. 检查服务状态
echo "1. 检查服务状态..."
docker compose ps
echo

# 2. 检查 Jaeger 是否可访问
echo "2. 检查 Jaeger UI..."
if curl -f http://localhost:16686 > /dev/null 2>&1; then
    echo "   [OK] Jaeger UI 可访问: http://localhost:16686"
else
    echo "   [FAIL] Jaeger UI 无法访问"
    exit 1
fi
echo

# 3. 检查后端 telemetry 初始化
echo "3. 检查后端 OpenTelemetry 初始化..."
docker compose logs backend | grep -i "telemetry\|otel" | tail -5
echo

# 4. 检查 MCP telemetry 初始化
echo "4. 检查 MCP OpenTelemetry 初始化..."
docker compose logs iot-mcp | grep -i "telemetry\|otel" | tail -5
echo

# 5. 触发测试请求
echo "5. 触发测试追踪..."
echo "   测试 MCP health check (应该产生追踪)..."
curl -s http://localhost:9000/ready > /dev/null
echo "   [OK]"
echo

# 6. 等待追踪数据上报
echo "6. 等待追踪数据上报到 Jaeger (3秒)..."
sleep 3
echo

# 7. 检查 Jaeger 是否收到追踪
echo "7. 检查 Jaeger 服务列表..."
SERVICES=$(curl -s http://localhost:16686/api/services | python -c "import sys, json; print('\n'.join(json.load(sys.stdin)['data']))" 2>/dev/null || echo "")
if echo "$SERVICES" | grep -q "xiaoyi-backend"; then
    echo "   [OK] 找到服务: xiaoyi-backend"
else
    echo "   [WARN] 未找到服务: xiaoyi-backend"
fi
if echo "$SERVICES" | grep -q "xiaoyi-iot-mcp"; then
    echo "   [OK] 找到服务: xiaoyi-iot-mcp"
else
    echo "   [WARN] 未找到服务: xiaoyi-iot-mcp"
fi
echo

echo "=== 验证完成 ==="
echo
echo "下一步："
echo "1. 访问 Jaeger UI: http://localhost:16686"
echo "2. 选择服务并查看追踪"
echo "3. 运行完整测试: python scripts/verify_telemetry.py"
echo
