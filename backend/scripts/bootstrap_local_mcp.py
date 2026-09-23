"""Register the Docker Compose MCP services in a local backend instance."""

from __future__ import annotations

import argparse
import json
import os

import httpx

SERVER_DEFINITIONS = (
    {
        "server_key": "iot-diagnosis-local",
        "name": "本地 IoT 智能诊断",
        "url": "http://iot-diagnosis-mcp:9001/mcp",
        "purpose": "iot",
        "service_kind": "diagnosis",
    },
    {
        "server_key": "iot-control-local",
        "name": "本地 IoT 设备控制",
        "url": "http://iot-control-mcp:9002/mcp",
        "purpose": "iot",
        "service_kind": "control",
    },
)

REPLACED_SERVER_KEYS = {"rag-local", "iot-local"}

READ_ONLY_TOOLS = {
    "diagnose_fault",
    "list_devices",
    "get_device_status",
    "get_device_logs",
    "get_diagnosis_trace",
    "list_diagnoses",
    "list_knowledge_documents",
    "list_fault_cases",
    "search_knowledge",
    "search_fault_cases",
    # IoT Control MCP：查询类工具
    "list_device_actions",
    "get_action_result",
    "list_remediation_proposals",
}

# proposal_only 与 read_only 一样会进入 Agent 工具列表，但语义上代表
# "可由 Agent 自主执行的低风险动作 / 可由 Agent 发起的高风险提案"。
PROPOSAL_ONLY_TOOLS = {
    "execute_device_action",
    "create_remediation_proposal",
}

# 仅后端审批 REST 直调（对 Agent 不可见），复用 add_verified_fault_case 模式。
APPROVAL_REQUIRED_TOOLS = {
    "add_verified_fault_case",
    "ingest_knowledge_text",
    "delete_knowledge_document",
    "delete_fault_case",
    "update_fault_case_lifecycle",
    "decide_remediation_proposal",
}


def data(response: httpx.Response) -> object:
    response.raise_for_status()
    return response.json()["data"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--credential", default=os.getenv("DIAGNOSIS_MCP_BEARER_TOKEN", ""))
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
            credential_update = {"credential": args.credential} if args.credential else {}
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
                            **credential_update,
                        },
                    )
                )
            else:
                server = data(
                    client.post(
                        f"{api}/mcp-servers",
                        headers=headers,
                        json={**definition, **credential_update},
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
                elif tool["original_name"] in PROPOSAL_ONLY_TOOLS:
                    policy = "proposal_only"
                elif tool["original_name"] in APPROVAL_REQUIRED_TOOLS:
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
