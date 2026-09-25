#!/usr/bin/env python3
"""Test MCP tool call to generate telemetry traces."""
import asyncio
import httpx

MCP_URL = "http://localhost:9000"


async def test_mcp_tool():
    """Call MCP list_devices tool to generate trace."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Calling MCP list_devices tool...")

        # MCP JSON-RPC request
        response = await client.post(
            MCP_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "list_devices",
                    "arguments": {}
                }
            }
        )

        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"[OK] MCP call successful")
            print(f"Result: {str(result)[:200]}...")
        else:
            print(f"[FAIL] MCP call failed: {response.text[:200]}")


async def check_traces():
    """Check Jaeger for traces."""
    print("\nWaiting 3 seconds for traces to export...")
    await asyncio.sleep(3)

    async with httpx.AsyncClient() as client:
        print("\nQuerying Jaeger for MCP traces...")
        response = await client.get(
            "http://localhost:16686/api/traces",
            params={"service": "xiaoyi-iot-mcp", "limit": 5}
        )

        if response.status_code == 200:
            traces = response.json()
            count = len(traces.get("data", []))
            print(f"[OK] Found {count} MCP traces in Jaeger")

            if count > 0:
                first_trace = traces["data"][0]
                spans = first_trace.get("spans", [])
                print(f"   First trace has {len(spans)} spans:")
                for span in spans[:5]:
                    op = span.get("operationName", "")
                    svc = span.get("process", {}).get("serviceName", "")
                    print(f"   - {svc}: {op}")
        else:
            print(f"[FAIL] Jaeger query failed: {response.status_code}")


async def main():
    print("=" * 60)
    print("MCP Telemetry Trace Test")
    print("=" * 60)

    await test_mcp_tool()
    await check_traces()

    print("\n" + "=" * 60)
    print("[OK] Test complete!")
    print("View traces: http://localhost:16686")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
