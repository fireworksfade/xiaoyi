"""Run a live browser-like smoke test against the frontend and FastAPI backend."""

from __future__ import annotations

import argparse
import json
import uuid
from urllib.parse import urlsplit

import httpx


def envelope(response: httpx.Response) -> dict:
    response.raise_for_status()
    return response.json()["data"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", default="http://localhost:3000")
    parser.add_argument("--backend", default="http://localhost:8000")
    parser.add_argument(
        "--api-base",
        help="API 根地址；默认通过前端同源代理访问",
    )
    args = parser.parse_args()

    origin = args.frontend.rstrip("/")
    api = args.api_base or f"{origin}/api/backend/api/v1"
    conversation_id: str | None = None

    with httpx.Client(timeout=30, follow_redirects=True, trust_env=False) as client:
        frontend = client.get(origin)
        frontend.raise_for_status()

        api_origin = urlsplit(api)
        frontend_origin = urlsplit(origin)
        same_origin = (api_origin.scheme, api_origin.netloc) == (
            frontend_origin.scheme,
            frontend_origin.netloc,
        )
        cors_status = "same-origin-proxy"
        if not same_origin:
            preflight = client.options(
                f"{api}/conversations",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type,x-csrf-token",
                },
            )
            preflight.raise_for_status()
            assert preflight.headers.get("access-control-allow-origin") == origin
            assert preflight.headers.get("access-control-allow-credentials") == "true"
            cors_status = "direct-cors"

        login = envelope(
            client.post(
                f"{api}/auth/login",
                headers={"Origin": origin},
                json={"username": "admin", "password": "admin123"},
            )
        )
        csrf_headers = {"Origin": origin, "X-CSRF-Token": login["csrf_token"]}

        try:
            created = envelope(
                client.post(
                    f"{api}/conversations",
                    headers=csrf_headers,
                    json={"title": "前后端联调临时对话"},
                )
            )
            conversation_id = created["id"]

            renamed = envelope(
                client.patch(
                    f"{api}/conversations/{conversation_id}",
                    headers=csrf_headers,
                    json={"title": "联调已重命名"},
                )
            )
            assert renamed["title"] == "联调已重命名"

            submitted = envelope(
                client.post(
                    f"{api}/conversations/{conversation_id}/messages",
                    headers=csrf_headers,
                    json={
                        "content": "请回复联调成功",
                        "client_message_id": f"smoke-{uuid.uuid4()}",
                    },
                )
            )

            event_names: list[str] = []
            with client.stream(
                "GET",
                f"{api}/agent-runs/{submitted['run_id']}/events",
                headers={"Origin": origin, "Accept": "text/event-stream"},
            ) as stream:
                stream.raise_for_status()
                assert stream.headers["content-type"].startswith("text/event-stream")
                for line in stream.iter_lines():
                    if line.startswith("event:"):
                        event_names.append(line.partition(":")[2].strip())

            assert "answer.delta" in event_names
            assert "run.completed" in event_names

            messages = envelope(
                client.get(
                    f"{api}/conversations/{conversation_id}/messages",
                    headers={"Origin": origin},
                )
            )
            assert [item["role"] for item in messages["items"]] == [
                "user",
                "assistant",
            ]
        finally:
            if conversation_id:
                deleted = envelope(
                    client.delete(
                        f"{api}/conversations/{conversation_id}",
                        headers=csrf_headers,
                    )
                )
                assert deleted["deleted"] is True

        print(
            json.dumps(
                {
                    "frontend": frontend.status_code,
                    "transport": cors_status,
                    "authentication": "ok",
                    "conversation_crud": "ok",
                    "sse": event_names,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
