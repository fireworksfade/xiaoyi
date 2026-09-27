"""Qdrant writes must remain covered independently of the legacy server tests."""

import uuid

from iot_diagnosis.external.qdrant_store import QdrantVectorStore


def test_batch_upsert_uses_stable_point_ids(monkeypatch):
    calls = []

    class BatchProvider:
        dimensions = 2

        def embed_many(self, texts):
            assert texts == ["first", "second"]
            return [[1.0, 0.0], [0.0, 1.0]]

    monkeypatch.setattr(QdrantVectorStore, "_ensure_collection", lambda self: None)
    store = QdrantVectorStore("http://qdrant:6333", "knowledge", BatchProvider())
    monkeypatch.setattr(
        store, "_request", lambda method, path, payload: calls.append((method, path, payload))
    )
    items = [
        {"source": "mqtt_docs", "id": "guide#0", "content": "first"},
        {"source": "wifi_docs", "id": "guide#0", "content": "second"},
    ]

    assert store.upsert_many(items)
    assert store.upsert_many(items)
    assert calls[0] == calls[1]
    method, path, payload = calls[0]
    assert (method, path) == ("PUT", "/collections/knowledge/points?wait=true")
    points = payload["points"]
    assert len({point["id"] for point in points}) == 2
    assert all(uuid.UUID(point["id"]).version == 5 for point in points)
    assert [point["payload"] for point in points] == items
    assert [point["vector"] for point in points] == [[1.0, 0.0], [0.0, 1.0]]
