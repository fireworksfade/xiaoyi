"""Register the Docker Compose MCP services in a local backend instance."""

from __future__ import annotations

import argparse
import json

import httpx


SERVER_DEFINITIONS = (
    {
        "server_key": "iot-diagnosis-local",
        "name": "本地 IoT 智能诊断",
        "url": "http://iot-diagnosis-mcp:9001/mcp",
        "purpose": "iot",
    },
)

REPLACED_SERVER_KEYS = {"rag-local", "iot-local"}

READ_ONLY_TOOLS = {
    "diagnose_fault",
    "get_device_status",
    "get_device_logs",
    "search_knowledge",
    "search_fault_cases",
}


def data(response: httpx.Response) -> object:
    response.raise_for_status()
    return response.json()["data"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    api = f"{args.backend.rstrip('/')}/api/v1"

    with httpx.Client(timeout=30, trust_env=False) as client:
        login = data(
            client.post(
                f"{api}/auth/login",
                json={"username": "admin", "password": "admin123"},
            )
        )
        headers = {"X-CSRF-Token": login["csrf_token"]}
        existing = {
            item["server_key"]: item
            for item in data(client.get(f"{api}/mcp-servers?page_size=100"))["items"]
        }
        for replaced_key in REPLACED_SERVER_KEYS:
            replaced = existing.get(replaced_key)
            if replaced:
                data(
                    client.delete(
                        f"{api}/mcp-servers/{replaced['id']}",
                        headers=headers,
                    )
                )
        summary: list[dict[str, object]] = []

        for definition in SERVER_DEFINITIONS:
            current = existing.get(definition["server_key"])
            if current:
                server = data(
                    client.patch(
                        f"{api}/mcp-servers/{current['id']}",
                        headers=headers,
                        json={
                            "name": definition["name"],
                            "url": definition["url"],
                            "purpose": definition["purpose"],
                            "enabled": True,
                        },
                    )
                )
            else:
                server = data(
                    client.post(
                        f"{api}/mcp-servers",
                        headers=headers,
                        json=definition,
                    )
                )
                server = data(
                    client.patch(
                        f"{api}/mcp-servers/{server['id']}",
                        headers=headers,
                        json={"enabled": True},
                    )
                )

            connection = data(
                client.post(f"{api}/mcp-servers/{server['id']}/test", headers=headers)
            )
            catalog = data(
                client.post(
                    f"{api}/mcp-servers/{server['id']}/refresh-tools",
                    headers=headers,
                )
            )
            enabled: list[str] = []
            for tool in catalog["items"]:
                if tool["original_name"] in READ_ONLY_TOOLS:
                    policy = "read_only"
                elif tool["original_name"] == "add_verified_fault_case":
                    policy = "approval_required"
                else:
                    policy = "disabled"
                is_enabled = policy != "disabled"
                data(
                    client.patch(
                        f"{api}/mcp-servers/{server['id']}/tools/{tool['id']}",
                        headers=headers,
                        json={"enabled": is_enabled, "risk_policy": policy},
                    )
                )
                if is_enabled:
                    enabled.append(tool["original_name"])

            summary.append(
                {
                    "server_key": server["server_key"],
                    "connected": connection["connected"],
                    "tool_count": connection["tool_count"],
                    "enabled_tools": enabled,
                }
            )

    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
