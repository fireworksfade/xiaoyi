"""Register the unified Docker Compose IoT MCP service in a local backend."""

from __future__ import annotations

import argparse
import json
import os
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

SERVER_DEFINITION = {
    "server_key": "iot-mcp-local",
    "name": "本地 IoT 诊断与控制",
    "url": "http://iot-mcp:9000/mcp",
    "purpose": "iot",
}

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
    "decide_remediation_proposal",
}


class APIClient:
    def __init__(self) -> None:
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))

    def data(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, object] | None = None,
        csrf_token: str | None = None,
    ) -> object:
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(url, data=body, headers=headers, method=method)
        with self.opener.open(request, timeout=30) as response:
            return json.load(response)["data"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--mcp-url", default=SERVER_DEFINITION["url"])
    parser.add_argument("--credential", default=os.getenv("DIAGNOSIS_MCP_BEARER_TOKEN", ""))
    args = parser.parse_args()
    api = f"{args.backend.rstrip('/')}/api/v1"

    client = APIClient()
    login = client.data(
        "POST",
        f"{api}/auth/login",
        payload={"username": "admin", "password": "admin123"},
    )
    csrf_token = login["csrf_token"]
    existing = {
        item["server_key"]: item
        for item in client.data("GET", f"{api}/mcp-servers?page_size=100")["items"]
    }
    summary: list[dict[str, object]] = []

    for definition in ({**SERVER_DEFINITION, "url": args.mcp_url},):
        credential_update = {"credential": args.credential} if args.credential else {}
        current = existing.get(definition["server_key"])
        if current:
            server = client.data(
                "PATCH",
                f"{api}/mcp-servers/{current['id']}",
                csrf_token=csrf_token,
                payload={
                    "name": definition["name"],
                    "url": definition["url"],
                    "purpose": definition["purpose"],
                    "enabled": True,
                    **credential_update,
                },
            )
        else:
            server = client.data(
                "POST",
                f"{api}/mcp-servers",
                csrf_token=csrf_token,
                payload={**definition, **credential_update},
            )
            server = client.data(
                "PATCH",
                f"{api}/mcp-servers/{server['id']}",
                csrf_token=csrf_token,
                payload={"enabled": True},
            )

        connection = client.data(
            "POST", f"{api}/mcp-servers/{server['id']}/test", csrf_token=csrf_token
        )
        catalog = client.data(
            "POST", f"{api}/mcp-servers/{server['id']}/refresh-tools", csrf_token=csrf_token
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
            client.data(
                "PATCH",
                f"{api}/mcp-servers/{server['id']}/tools/{tool['id']}",
                csrf_token=csrf_token,
                payload={"enabled": is_enabled, "risk_policy": policy},
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

    client.data("POST", f"{api}/auth/logout", csrf_token=csrf_token)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
