"""Versioned Qdrant projections. Never return payload text as memory content."""

import uuid

import httpx
from sqlalchemy import select
from xiaoyi_retrieval.embeddings import AsyncEmbeddingClient, EmbeddingConfig
from xiaoyi_retrieval.qdrant import AsyncQdrantClient, collection_payload

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
    config = EmbeddingConfig(
        s.memory_embedding_url,
        s.memory_embedding_model,
        s.memory_embedding_dimensions,
        s.memory_embedding_api_key,
    )
    try:
        return await AsyncEmbeddingClient(config, client).embed(text)
    except ValueError as exc:
        if str(exc) == "EMBEDDING_DIMENSIONS_MISMATCH":
            raise ValueError("MEMORY_VECTOR_DIMENSION_MISMATCH") from exc
        raise


async def vector_search(owner, query):
    s = get_settings()
    if not owner or not s.memory_qdrant_url or not s.memory_embedding_url:
        return {}
    filters = [
        {"key": "owner_user_id", "match": {"value": owner}},
        {"key": "status", "match": {"value": "active"}},
    ]
    filters.append({"key": "model_fingerprint", "match": {"value": s.memory_embedding_fingerprint}})
    async with httpx.AsyncClient(timeout=s.memory_recall_timeout_ms / 1000) as client:
        vector = await embedding(client, query.query)
        return await AsyncQdrantClient(client, s.memory_qdrant_url).query(
            collection(), vector, filters=filters, limit=30
        )


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
        payload = {
            **(rev.applicability_json if rev else {}),
            "owner_user_id": outbox.owner_user_id,
            "memory_id": outbox.memory_id,
            "revision": outbox.revision,
            "status": "active",
            "kind": item.kind if item else "",
            "content_hash": rev.content_hash if rev else "",
            "model_fingerprint": outbox.model_fingerprint,
        }
    if not s.memory_qdrant_url or not s.memory_embedding_url:
        # Portable mode has no vector promise. SQL keyword retrieval remains available.
        state = "excluded"
    else:
        if (
            outbox.model_fingerprint != s.memory_embedding_fingerprint
            or outbox.collection != collection()
        ):
            valid = False
        async with httpx.AsyncClient(timeout=20) as client:
            qdrant = AsyncQdrantClient(client, s.memory_qdrant_url)
            base = f"/collections/{outbox.collection}"
            if valid and outbox.operation == "upsert":
                await qdrant.request(
                    "PUT",
                    base,
                    collection_payload(s.memory_embedding_dimensions),
                    accepted_statuses=(200, 409),
                )
                vector = await embedding(client, text)
                await qdrant.request(
                    "PUT",
                    base + "/points?wait=true",
                    {
                        "points": [
                            {
                                "id": point_id(item.id, outbox.revision, outbox.model_fingerprint),
                                "vector": vector,
                                "payload": payload,
                            }
                        ]
                    },
                )
                state = "indexed"
            else:
                await qdrant.request(
                    "POST",
                    base + "/points/delete?wait=true",
                    {
                        "points": [
                            point_id(outbox.memory_id, outbox.revision, outbox.model_fingerprint)
                        ]
                    },
                    accepted_statuses=(404,),
                )
                state = "excluded"
    async with SessionFactory() as db:
        current = await db.get(Memory, outbox.memory_id)
        if state == "indexed" and (not current or not await eligible(db, current, outbox.revision)):
            from app.memory.service import enqueue

            cleanup = MemoryVectorOutbox(
                owner_user_id=outbox.owner_user_id,
                memory_id=outbox.memory_id,
                revision=outbox.revision,
                operation="purge",
                model_fingerprint=outbox.model_fingerprint,
                collection=outbox.collection,
            )
            db.add(cleanup)
            await db.flush()
            await enqueue(
                db,
                outbox.owner_user_id,
                "sync_vector",
                f"index:{cleanup.id}",
                {"outbox_id": cleanup.id},
            )
            state = "excluded"
        row = await db.scalar(
            select(MemoryIndexState).where(
                MemoryIndexState.memory_id == outbox.memory_id,
                MemoryIndexState.revision == outbox.revision,
                MemoryIndexState.model_fingerprint == outbox.model_fingerprint,
            )
        )
        if not row:
            row = MemoryIndexState(
                memory_id=outbox.memory_id,
                revision=outbox.revision,
                model_fingerprint=outbox.model_fingerprint,
            )
            db.add(row)
        row.status = state
        if state == "indexed":
            from app.observability.metrics import MEMORY_EVENTS

            MEMORY_EVENTS.labels(event="index_updated").inc()
        entry = await db.get(MemoryVectorOutbox, outbox.id)
        entry.status = "done"
        await db.commit()
