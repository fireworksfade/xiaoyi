#!/usr/bin/env python3
"""Test MCP client connection and trace generation."""
import asyncio
import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def test_mcp_tools():
    """Test MCP tools through streamable-http client."""
    print("Connecting to MCP server at http://localhost:9000/mcp...")

    async with streamable_http_client("http://localhost:9000/mcp") as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            await session.initialize()
            print("[OK] Connected to MCP server")

            # List available tools
            tools = await session.list_tools()
            print(f"[OK] Found {len(tools.tools)} tools")
            for tool in tools.tools[:3]:
                print(f"   - {tool.name}")

            # Call list_devices tool
            print("\nCalling list_devices tool...")
            result = await session.call_tool("list_devices", {})
            print(f"[OK] list_devices returned {len(result.content)} content items")

            print("\nWaiting 3 seconds for trace export...")
            await asyncio.sleep(3)


async def check_jaeger():
    """Check if traces appear in Jaeger."""
    print("\nQuerying Jaeger for traces...")

    async with httpx.AsyncClient() as client:
        # Check backend traces
        response = await client.get(
            "http://localhost:16686/api/traces",
            params={"service": "xiaoyi-backend", "limit": 5}
        )
        if response.status_code == 200:
            count = len(response.json().get("data", []))
            print(f"[OK] Backend traces: {count}")

        # Check MCP traces
        response = await client.get(
            "http://localhost:16686/api/traces",
            params={"service": "xiaoyi-iot-mcp", "limit": 5}
        )
        if response.status_code == 200:
            traces = response.json()
            count = len(traces.get("data", []))
            print(f"[OK] MCP traces: {count}")

            if count > 0:
                first_trace = traces["data"][0]
                spans = first_trace.get("spans", [])
                print(f"\n   First MCP trace has {len(spans)} spans:")
                for span in spans[:5]:
                    op = span.get("operationName", "")
                    svc = span.get("process", {}).get("serviceName", "")
                    print(f"   - {svc}: {op}")


async def main():
    print("=" * 60)
    print("MCP Client Telemetry Test")
    print("=" * 60)
    print()

    try:
        await test_mcp_tools()
        await check_jaeger()
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()

    print()
    print("=" * 60)
    print("[OK] Test complete!")
    print("View traces: http://localhost:16686")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
