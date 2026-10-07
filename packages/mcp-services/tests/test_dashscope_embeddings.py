import json

import pytest

from iot_diagnosis.embeddings import embedding_provider_from_env


@pytest.fixture
def dashscope(monkeypatch):
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_PROVIDER", "DashScope")
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_BASE_URL", "https://models.example/compatible-mode/v1")
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_MODEL", "embedding-test")
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_DIMENSIONS", "2")
    monkeypatch.delenv("DIAGNOSIS_EMBEDDING_QUERY_INSTRUCTION", raising=False)
    return embedding_provider_from_env()


@pytest.mark.parametrize("index_field", ["index", "text_index"])
def test_dashscope_native_batches_preserve_order(monkeypatch, dashscope, index_field):
    calls = []

    class Response:
        def __init__(self, inputs):
            self.inputs = inputs

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            # 反向响应验证每一批按 index 恢复原始输入顺序。
            return json.dumps(
                {
                    "output": {
                        "embeddings": [
                            {index_field: index, "embedding": [float(text), 1.0]}
                            for index, text in reversed(list(enumerate(self.inputs)))
                        ]
                    }
                }
            ).encode()

    def fake_urlopen(request, **_kwargs):
        assert (
            request.full_url
            == "https://models.example/api/v1/services/embeddings/text-embedding/text-embedding"
        )
        assert request.get_header("Authorization") == "Bearer test-key"
        payload = json.loads(request.data)
        assert payload["model"] == "embedding-test"
        assert payload["parameters"] == {
            "dimension": 2,
            "text_type": "query",
            "output_type": "dense",
        }
        calls.append(payload["input"]["texts"])
        return Response(payload["input"]["texts"])

    monkeypatch.setattr("iot_diagnosis.embeddings.urlopen", fake_urlopen)
    vectors = dashscope.embed_many([str(i) for i in range(23)], is_query=True)
    assert [len(batch) for batch in calls] == [10, 10, 3]
    assert vectors == [[float(i), 1.0] for i in range(23)]
    assert dashscope.query_instruction == ""


def test_dashscope_rejects_duplicate_native_indices(monkeypatch, dashscope):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "output": {
                        "embeddings": [
                            {"index": 0, "embedding": [1.0, 0.0]},
                            {"index": 0, "embedding": [0.0, 1.0]},
                        ]
                    }
                }
            ).encode()

    monkeypatch.setattr("iot_diagnosis.embeddings.urlopen", lambda *_a, **_kw: Response())
    with pytest.raises(RuntimeError, match="EMBEDDING_REQUEST_FAILED") as error:
        dashscope.embed_many(["one", "two"])
    assert str(error.value.__cause__) == "EMBEDDING_RESPONSE_INDICES_INVALID"


def test_dashscope_query_instruction_can_be_explicitly_configured(monkeypatch, dashscope):
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_QUERY_INSTRUCTION", "Retrieve IoT passages")
    assert embedding_provider_from_env().query_instruction == "Retrieve IoT passages"


def test_dashscope_uses_shared_dimensions_if_specific_setting_is_empty(monkeypatch, dashscope):
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_DIMENSIONS", "")
    monkeypatch.setenv("RETRIEVAL_EMBEDDING_DIMENSIONS", "512")
    assert embedding_provider_from_env().dimensions == 512
