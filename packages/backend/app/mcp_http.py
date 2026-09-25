from typing import Any

import httpx2


def mcp_httpx_client_factory(
    headers: dict[str, str] | None = None,
    timeout: Any = None,
    auth: Any = None,
) -> httpx2.AsyncClient:
    """Create a direct MCP transport client for private/local service URLs."""
    kwargs: dict[str, Any] = {
        "follow_redirects": False,
        "trust_env": False,
    }
    if headers is not None:
        kwargs["headers"] = headers
    if timeout is not None:
        kwargs["timeout"] = timeout
    if auth is not None:
        kwargs["auth"] = auth
    return httpx2.AsyncClient(**kwargs)
