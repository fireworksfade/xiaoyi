"""Qdrant transport helpers; collections, filters and payloads belong to callers."""

from .http import AsyncJsonClient


def collection_payload(dimensions):
    return {"vectors": {"size": dimensions, "distance": "Cosine"}}


def query_payload(vector, limit, filters=None):
    payload = {"query": vector, "limit": limit, "with_payload": True}
    if filters:
        payload["filter"] = {"must": filters}
    return payload


class AsyncQdrantClient(AsyncJsonClient):
    async def query(self, collection, vector, *, limit, filters):
        response = await self.request(
            "POST",
            f"/collections/{collection}/points/query",
            query_payload(vector, limit, filters),
        )
        return (response.get("result") or {}).get("points") or []
