from __future__ import annotations

import hmac
import os

from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl


class StaticBearerTokenVerifier:
    def __init__(self, expected_token: str):
        self.expected_token = expected_token

    async def verify_token(self, token: str) -> AccessToken | None:
        if not self.expected_token or not hmac.compare_digest(token, self.expected_token):
            return None
        return AccessToken(
            token=token,
            client_id="iot-diagnosis-backend",
            scopes=["mcp:invoke"],
            subject="iot-diagnosis-client",
        )


def auth_configuration() -> tuple[AuthSettings | None, StaticBearerTokenVerifier | None]:
    token = os.getenv("DIAGNOSIS_MCP_BEARER_TOKEN", "").strip()
    if not token:
        return None, None
    public_url = os.getenv("DIAGNOSIS_MCP_PUBLIC_URL", "http://127.0.0.1:9001").rstrip("/")
    settings = AuthSettings(
        issuer_url=AnyHttpUrl(public_url),
        resource_server_url=AnyHttpUrl(f"{public_url}/mcp"),
        required_scopes=["mcp:invoke"],
    )
    return settings, StaticBearerTokenVerifier(token)
