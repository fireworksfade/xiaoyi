"""Versioned Qdrant projections. Never return payload text as memory content."""
import uuid

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionFactory
from app.memory.models import Memory, MemoryIndexState, MemoryVectorOutbox
from app.memory.service import eligible, revision


def collection():
    s = get_settings()
    return f"{s.memory_collection_prefix}_{s.memory_embedding_fingerprint}_{s.memory_embedding_dimensions}_v1"


def point_id(memory_id, number, fingerprint):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"memory:{memory_id}:{number}:{fingerprint}"))


async def embedding(client, text):
    s = get_settings()
    response = await client.post(s.memory_embedding_url.rstrip('/') + "/v1/embeddings",
        json={"model": s.memory_embedding_model, "input": text, "dimensions": s.memory_embedding_dimensions})
    response.raise_for_status()
    vector = response.json()["data"][0]["embedding"]
    if len(vector) != s.memory_embedding_dimensions:
        raise ValueError("MEMORY_VECTOR_DIMENSION_MISMATCH")
    return vector


async def vector_search(owner, query):
    s = get_settings()
    if not owner or not s.memory_qdrant_url or not s.memory_embedding_url:
        return {}
    filters = [{"key": "owner_user_id", "match": {"value": owner}}, {"key": "status", "match": {"value": "active"}}]
    async with httpx.AsyncClient(timeout=s.memory_recall_timeout_ms / 1000) as client:
        vector = await embedding(client, query.query)
        response = await client.post(s.memory_qdrant_url.rstrip('/') + f"/collections/{collection()}/points/query",
            json={"query": vector, "filter": {"must": filters}, "limit": 30, "with_payload": True})
        response.raise_for_status()
        return {point["payload"]["memory_id"]: point["score"] for point in response.json()["result"]["points"]}


async def sync(job):
    s = get_settings()
    async with SessionFactory() as db:
        outbox = await db.get(MemoryVectorOutbox, job.payload["outbox_id"])
        if not outbox or outbox.status == "done":
            return
        item = await db.get(Memory, outbox.memory_id)
        valid = item and await eligible(db, item, outbox.revision)
        rev = await revision(db, item, outbox.revision) if item else None
        text = rev.search_text if rev else ""
        payload = {"owner_user_id": outbox.owner_user_id, "memory_id": outbox.memory_id,
            "revision": outbox.revision, "status": "active", "kind": item.kind if item else "",
            "content_hash": rev.content_hash if rev else "", "model_fingerprint": outbox.model_fingerprint,
            **(rev.applicability_json if rev else {})}
    if not s.memory_qdrant_url or not s.memory_embedding_url:
        # Portable mode has no vector promise. SQL keyword retrieval remains available.
        state = "excluded"
    else:
        if outbox.model_fingerprint != s.memory_embedding_fingerprint or outbox.collection != collection():
            valid = False
        async with httpx.AsyncClient(timeout=20) as client:
            base = s.memory_qdrant_url.rstrip('/') + f"/collections/{outbox.collection}"
            if valid and outbox.operation == "upsert":
                response = await client.put(base, json={"vectors": {"size": s.memory_embedding_dimensions, "distance": "Cosine"}})
                if response.status_code not in (200, 409):
                    response.raise_for_status()
                vector = await embedding(client, text)
                response = await client.put(base + "/points?wait=true", json={"points": [{
                    "id": point_id(item.id, outbox.revision, outbox.model_fingerprint), "vector": vector, "payload": payload}]})
                response.raise_for_status()
                state = "indexed"
            else:
                response = await client.post(base + "/points/delete?wait=true", json={"points": [point_id(outbox.memory_id, outbox.revision, outbox.model_fingerprint)]})
                if response.status_code != 404:
                    response.raise_for_status()
                state = "excluded"
    async with SessionFactory() as db:
        current = await db.get(Memory, outbox.memory_id)
        if state == "indexed" and (not current or not await eligible(db, current, outbox.revision)):
            from app.memory.service import index_change
            if current:
                await index_change(db, current, "purge")
            state = "excluded"
        row = await db.scalar(select(MemoryIndexState).where(MemoryIndexState.memory_id == outbox.memory_id,
            MemoryIndexState.revision == outbox.revision, MemoryIndexState.model_fingerprint == outbox.model_fingerprint))
        if not row:
            row = MemoryIndexState(memory_id=outbox.memory_id, revision=outbox.revision, model_fingerprint=outbox.model_fingerprint)
            db.add(row)
        row.status = state
        entry = await db.get(MemoryVectorOutbox, outbox.id)
        entry.status = "done"
        await db.commit()
