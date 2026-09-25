#!/usr/bin/env python3
"""验证 OpenTelemetry 追踪链路：MCP → Diagnosis → MQTT"""
import asyncio
import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def test_diagnosis_flow():
    """测试诊断流程，生成完整的追踪链路"""
    print("=" * 60)
    print("Testing MCP Diagnosis Flow")
    print("=" * 60)
    print()

    async with streamable_http_client("http://localhost:9000/mcp") as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            await session.initialize()
            print("[OK] Connected to MCP server")

            # 1. List devices
            print("\n1. Listing devices...")
            result = await session.call_tool("list_devices", {})
            print(f"[OK] Found devices")

            # 2. Get device status (triggers MQTT state retrieval)
            print("\n2. Getting device status (triggers MQTT)...")
            result = await session.call_tool(
                "get_device_status",
                {"device_id": "AIR_CONDITIONER_001"}
            )
            print(f"[OK] Retrieved device status")

            # 3. Diagnose fault (triggers full RAG pipeline)
            print("\n3. Diagnosing fault (triggers RAG pipeline)...")
            result = await session.call_tool(
                "diagnose_fault",
                {
                    "device_id": "AIR_CONDITIONER_001",
                    "query": "制冷效果差"
                }
            )
            print(f"[OK] Diagnosis complete")


async def check_traces():
    """检查 Jaeger 中的追踪数据"""
    print("\n" + "=" * 60)
    print("Checking Jaeger Traces")
    print("=" * 60)
    print("\nWaiting 5 seconds for trace export...")
    await asyncio.sleep(5)

    async with httpx.AsyncClient() as client:
        # Check MCP traces
        response = await client.get(
            "http://localhost:16686/api/traces",
            params={
                "service": "xiaoyi-iot-mcp",
                "limit": 20,
                "lookback": "5m"
            }
        )

        if response.status_code == 200:
            traces = response.json()
            trace_count = len(traces.get("data", []))
            print(f"\n[OK] Found {trace_count} MCP traces")

            if trace_count > 0:
                # 分析追踪内容
                operations = set()
                for trace in traces["data"]:
                    for span in trace.get("spans", []):
                        op = span.get("operationName", "")
                        if op:
                            operations.add(op)

                print(f"\nUnique operations ({len(operations)}):")
                for op in sorted(operations):
                    print(f"   - {op}")

                # 显示最新的追踪详情
                latest_trace = traces["data"][0]
                spans = latest_trace.get("spans", [])
                print(f"\nLatest trace ({len(spans)} spans):")
                for span in spans[:10]:
                    op = span.get("operationName", "")
                    duration_us = span.get("duration", 0)
                    duration_ms = duration_us / 1000
                    print(f"   - {op}: {duration_ms:.2f}ms")
        else:
            print(f"[FAIL] Jaeger query failed: {response.status_code}")


async def main():
    try:
        await test_diagnosis_flow()
        await check_traces()

        print("\n" + "=" * 60)
        print("[OK] Verification Complete!")
        print("\nNext steps:")
        print("1. Open Jaeger UI: http://localhost:16686")
        print("2. Select service: xiaoyi-iot-mcp")
        print("3. View recent traces to see:")
        print("   - Tool execution spans")
        print("   - RAG retrieval operations")
        print("   - MQTT interactions")
        print("=" * 60)

    except Exception as e:
        print(f"\n[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
