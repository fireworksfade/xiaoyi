import json

import pytest

from iot_diagnosis.reranker import RemoteReranker, reranker_from_env


class Response:
    def __init__(self, results):
        self.results = results

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"results": self.results}).encode()


@pytest.fixture
def candidates():
    return [
        {"id": "a", "source": "mqtt_docs", "content": "MQTT timeout", "retrieval_score": 0.9},
        {"id": "b", "source": "wifi_docs", "content": "WiFi RSSI", "retrieval_score": 0.5},
    ]


def test_api_configuration_sends_auth_model_and_accepts_relevance_scores(monkeypatch, candidates):
    monkeypatch.setenv("DIAGNOSIS_RERANKER_PROVIDER", "remote")
    monkeypatch.setenv("DIAGNOSIS_RERANKER_URL", "https://models.example/v1/rerank")
    monkeypatch.setenv("DIAGNOSIS_RERANKER_MODEL", "api-model")
    monkeypatch.setenv("DIAGNOSIS_RERANKER_API_KEY", "test-key")
    monkeypatch.setenv("DIAGNOSIS_RERANKER_TIMEOUT_SECONDS", "12")

    def fake_urlopen(request, *, timeout):
        assert request.full_url == "https://models.example/v1/rerank"
        assert request.get_header("Authorization") == "Bearer test-key"
        assert timeout == 12
        assert json.loads(request.data) == {
            "model": "api-model",
            "query": "MQTT timeout",
            "documents": ["MQTT timeout", "WiFi RSSI"],
            "top_n": 2,
        }
        return Response(
            [
                {"index": 1, "relevance_score": 0.98},
                {"index": 0, "relevance_score": 0.2},
            ]
        )

    monkeypatch.setattr("iot_diagnosis.reranker.urlopen", fake_urlopen)
    reranker = reranker_from_env()
    ranked = reranker.rerank("MQTT timeout", candidates, expected_source="mqtt_docs", top_k=2)
    assert [item["id"] for item in ranked] == ["b", "a"]
    assert [item["score"] for item in ranked] == [0.98, 0.2]
    assert not reranker.used_fallback


def test_dashscope_native_factory_and_response(monkeypatch, candidates):
    monkeypatch.setenv("DIAGNOSIS_RERANKER_PROVIDER", "DashScope")
    monkeypatch.setenv("DIAGNOSIS_RERANKER_URL", "https://models.example/native-rerank")
    monkeypatch.setenv("DIAGNOSIS_RERANKER_MODEL", "native-model")
    monkeypatch.setenv("DIAGNOSIS_RERANKER_API_KEY", "test-key")

    class NativeResponse(Response):
        def read(self):
            return json.dumps({"output": {"results": self.results}}).encode()

    def fake_urlopen(request, **_kwargs):
        assert request.get_header("Authorization") == "Bearer test-key"
        assert json.loads(request.data) == {
            "model": "native-model",
            "input": {"query": "MQTT timeout", "documents": ["MQTT timeout", "WiFi RSSI"]},
            "parameters": {"top_n": 2, "return_documents": False},
        }
        return NativeResponse(
            [
                {"index": 1, "relevance_score": 0.98},
                {"index": 0, "relevance_score": 0.2},
            ]
        )

    monkeypatch.setattr("iot_diagnosis.reranker.urlopen", fake_urlopen)
    reranker = reranker_from_env()
    ranked = reranker.rerank("MQTT timeout", candidates, expected_source="mqtt_docs", top_k=2)
    assert [item["id"] for item in ranked] == ["b", "a"]
    assert [item["score"] for item in ranked] == [0.98, 0.2]
    assert reranker.name == "dashscope_remote"
    assert not reranker.used_fallback


@pytest.mark.parametrize("missing", ["URL", "MODEL", "API_KEY"])
def test_dashscope_requires_complete_configuration(monkeypatch, missing):
    monkeypatch.setenv("DIAGNOSIS_RERANKER_PROVIDER", "dashscope")
    for suffix, value in [
        ("URL", "https://models.example/rerank"),
        ("MODEL", "model"),
        ("API_KEY", "test-key"),
    ]:
        monkeypatch.setenv("DIAGNOSIS_RERANKER_" + suffix, "" if suffix == missing else value)
    with pytest.raises(ValueError, match="RERANKER_PROVIDER_NOT_CONFIGURED"):
        reranker_from_env()


def test_dashscope_invalid_nested_results_fall_back(monkeypatch, candidates):
    class NativeResponse(Response):
        def read(self):
            return json.dumps(
                {"output": {"results": [{"index": 0, "relevance_score": 1}]}}
            ).encode()

    monkeypatch.setattr("iot_diagnosis.reranker.urlopen", lambda *_a, **_kw: NativeResponse([]))
    reranker = RemoteReranker("https://models.example/rerank", api_format="dashscope")
    ranked = reranker.rerank("MQTT timeout", candidates, expected_source="mqtt_docs", top_k=2)
    assert reranker.used_fallback
    assert [item["id"] for item in ranked] == ["a", "b"]


def test_local_service_omits_optional_auth_and_model(monkeypatch, candidates):
    def fake_urlopen(request, **_kwargs):
        assert request.get_header("Authorization") is None
        assert "model" not in json.loads(request.data)
        return Response([{"index": 0, "score": 0.9}, {"index": 1, "score": 0.1}])

    monkeypatch.setattr("iot_diagnosis.reranker.urlopen", fake_urlopen)
    reranker = RemoteReranker("http://models/rerank")
    ranked = reranker.rerank("MQTT timeout", candidates, expected_source="mqtt_docs", top_k=1)
    assert ranked[0]["id"] == "a"
    assert not reranker.used_fallback


def test_api_local_weighted_reranker_priority_and_recovery(monkeypatch, candidates):
    from urllib.error import URLError

    monkeypatch.setenv("DIAGNOSIS_RERANKER_PROVIDER", "DashScope")
    monkeypatch.setenv("DIAGNOSIS_RERANKER_URL", "https://cloud.example/rerank")
    monkeypatch.setenv("DIAGNOSIS_RERANKER_MODEL", "cloud-model")
    monkeypatch.setenv("DIAGNOSIS_RERANKER_API_KEY", "test-key")
    monkeypatch.setenv("DIAGNOSIS_LOCAL_RERANKER_FALLBACK", "true")
    monkeypatch.setenv("DIAGNOSIS_LOCAL_RERANKER_URL", "http://local-models/rerank")
    failures = {"api": False, "local": False}
    calls = []

    class NativeResponse(Response):
        def read(self):
            return json.dumps({"output": {"results": self.results}}).encode()

    def open_request(request, **_kwargs):
        tier = "api" if request.full_url.startswith("https://cloud.example") else "local"
        calls.append(tier)
        if failures[tier]:
            raise URLError("simulated outage")
        rows = [{"index": 0, "score": 0.9}, {"index": 1, "score": 0.1}]
        return NativeResponse(rows) if tier == "api" else Response(rows)

    monkeypatch.setattr("iot_diagnosis.reranker.urlopen", open_request)
    reranker = reranker_from_env()

    def rank():
        return reranker.rerank("MQTT timeout", candidates, expected_source="mqtt_docs", top_k=2)

    assert rank() and reranker.active_provider == "dashscope_remote"
    assert calls == ["api"] and not reranker.used_fallback
    failures["api"] = True
    assert rank() and reranker.active_provider == "qwen3_local"
    assert calls[-2:] == ["api", "local"] and reranker.used_fallback
    failures["local"] = True
    assert rank() and reranker.active_provider == "weighted"
    failures["api"] = False
    assert rank() and reranker.active_provider == "dashscope_remote"
    assert calls[-1] == "api" and not reranker.used_fallback


@pytest.mark.parametrize(
    "results",
    [
        [],
        [{"index": 0, "score": 1}],
        [{"index": -1, "score": 1}, {"index": 0, "score": 0.5}],
        [{"index": 2, "score": 1}, {"index": 0, "score": 0.5}],
        [{"index": 0, "score": 1}, {"index": 0, "score": 0.5}],
        [{"index": False, "score": 1}, {"index": 1, "score": 0.5}],
        [{"index": 0.5, "score": 1}, {"index": 1, "score": 0.5}],
        [{"index": 0, "relevance_score": float("nan")}, {"index": 1, "score": 0.5}],
        [{"index": 0, "score": float("inf")}, {"index": 1, "score": 0.5}],
        [{"index": 0}, {"index": 1, "score": 0.5}],
    ],
)
def test_invalid_api_results_fall_back_and_recover(monkeypatch, candidates, results):
    monkeypatch.setattr("iot_diagnosis.reranker.urlopen", lambda *_a, **_kw: Response(results))
    reranker = RemoteReranker("https://models.example/rerank", api_key="test-key")
    ranked = reranker.rerank("MQTT timeout", candidates, expected_source="mqtt_docs", top_k=2)
    assert reranker.used_fallback
    assert [item["id"] for item in ranked] == ["a", "b"]

    valid = [{"index": 0, "score": 0.9}, {"index": 1, "score": 0.1}]
    monkeypatch.setattr("iot_diagnosis.reranker.urlopen", lambda *_a, **_kw: Response(valid))
    reranker.rerank("MQTT timeout", candidates, expected_source="mqtt_docs", top_k=2)
    assert not reranker.used_fallback
