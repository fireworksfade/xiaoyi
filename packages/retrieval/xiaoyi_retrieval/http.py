"""JSON transports with explicit timeouts and no automatic replay of writes."""

import json
from urllib.request import Request, urlopen


class JsonClient:
    def __init__(self, base_url, *, timeout_seconds=10, api_key=None, opener=None):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key
        self.opener = opener or urlopen

    def request(self, method, path, payload=None):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            method=method,
            headers=headers,
        )
        with self.opener(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


class AsyncJsonClient:
    def __init__(self, client, base_url, *, api_key=None):
        # The caller owns the async client's lifetime and timeout.
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def request(self, method, path, payload=None, *, accepted_statuses=()):
        kwargs = {"json": payload} if payload is not None else {}
        if self.api_key:
            kwargs["headers"] = {"Authorization": f"Bearer {self.api_key}"}
        response = await getattr(self.client, method.lower())(
            self.base_url + path, **kwargs
        )
        if response.status_code >= 400 and response.status_code in accepted_statuses:
            return {}
        if response.status_code not in accepted_statuses:
            response.raise_for_status()
        return response.json()
