import json

import httpx
import pytest

from xiaoyi_retrieval.embeddings import (
    AsyncEmbeddingClient,
    EmbeddingClient,
    EmbeddingConfig,
)
from xiaoyi_retrieval.qdrant import AsyncQdrantClient


@pytest.mark.parametrize(
    "base", ["http://models", "http://models/v1/", "http://models/v1/embeddings"]
)
async def test_sync_and_async_embedding_contracts_match(base):
    config = EmbeddingConfig(base, "test-model", 2, "test-key")
    calls = []
    response = {"data": [{"index": 0, "embedding": [0.25, 0.75]}]}

    def handle(request):
        calls.append(
            (
                str(request.url),
                json.loads(request.content),
                request.headers["authorization"],
            )
        )
        return httpx.Response(200, json=response)

    class SyncResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self):
            return json.dumps(response).encode()

    def opener(request, timeout):
        assert timeout == 7
        calls.append(
            (
                request.full_url,
                json.loads(request.data),
                request.get_header("Authorization"),
            )
        )
        return SyncResponse()

    sync = EmbeddingClient(config, timeout_seconds=7, opener=opener)
    assert sync.embed_many(["MQTT failure"]) == [[0.25, 0.75]]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        assert await AsyncEmbeddingClient(config, client).embed("MQTT failure") == [
            0.25,
            0.75,
        ]
    assert calls[0] == calls[1]
    assert calls[0][0] == "http://models/v1/embeddings"


@pytest.mark.parametrize(
    "rows,error",
    [
        ([{"index": 0, "embedding": [0.0]}], "DIMENSIONS_MISMATCH"),
        ([{"index": 1, "embedding": [0.0, 1.0]}], "INDICES_INVALID"),
        ([{"index": 0, "embedding": [float("nan"), 1.0]}], "VALUES_INVALID"),
        ([{"index": 0, "embedding": [0.0, 1.0]}] * 2, "INDICES_INVALID"),
    ],
)
def test_invalid_vectors_are_rejected(rows, error):
    with pytest.raises(ValueError, match=error):
        EmbeddingConfig("http://models", "test", 2).vectors({"data": rows}, 1)


def test_batch_response_order_and_query_instruction():
    config = EmbeddingConfig(
        "http://models", "test", 2, query_instruction="Retrieve guides"
    )
    rows = [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]
    assert config.vectors({"data": rows}, 2) == [[1, 0], [0, 1]]
    assert config.payload(["wifi"], is_query=True)["input"] == [
        "Instruct: Retrieve guides\nQuery:wifi"
    ]
    assert config.payload(["wifi"])["input"] == ["wifi"]


async def test_qdrant_preserves_owner_filters_and_never_retries_writes():
    requests = []
    filters = [{"key": "owner_user_id", "match": {"value": "user-1"}}]

    def handle(request):
        requests.append(request)
        if request.url.path.endswith("query"):
            assert json.loads(request.content)["filter"] == {"must": filters}
            return httpx.Response(200, json={"result": {"points": [{"id": "point"}]}})
        return httpx.Response(503, text="unavailable")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        qdrant = AsyncQdrantClient(client, "http://qdrant")
        assert await qdrant.query("memory", [1, 0], limit=3, filters=filters) == [
            {"id": "point"}
        ]
        with pytest.raises(httpx.HTTPStatusError):
            await qdrant.request(
                "PUT", "/collections/memory/points?wait=true", {"points": []}
            )
    assert len(requests) == 2


async def test_accepted_missing_collection_does_not_require_json():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(404))
    ) as client:
        assert (
            await AsyncQdrantClient(client, "http://qdrant").request(
                "POST",
                "/collections/missing/points/delete",
                {},
                accepted_statuses=(404,),
            )
            == {}
        )
