from iot_diagnosis.embeddings import embedding_provider_from_env


def test_shared_model_configuration_and_diagnosis_override(monkeypatch):
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_PROVIDER", "openai_compatible")
    for suffix in ("BASE_URL", "MODEL", "API_KEY", "DIMENSIONS"):
        monkeypatch.delenv(f"DIAGNOSIS_EMBEDDING_{suffix}", raising=False)
    monkeypatch.setenv("RETRIEVAL_EMBEDDING_BASE_URL", "http://shared-model/v1")
    monkeypatch.setenv("RETRIEVAL_EMBEDDING_MODEL", "shared-model")
    monkeypatch.setenv("RETRIEVAL_EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("RETRIEVAL_EMBEDDING_DIMENSIONS", "256")
    provider = embedding_provider_from_env()
    assert (provider.base_url, provider.model, provider.dimensions) == (
        "http://shared-model/v1",
        "shared-model",
        256,
    )
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_DIMENSIONS", "512")
    assert embedding_provider_from_env().dimensions == 512


def test_shared_model_dimensions_do_not_change_portable_hash_collection(monkeypatch):
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_PROVIDER", "hash")
    monkeypatch.delenv("DIAGNOSIS_EMBEDDING_DIMENSIONS", raising=False)
    monkeypatch.setenv("RETRIEVAL_EMBEDDING_DIMENSIONS", "512")
    provider = embedding_provider_from_env()
    assert provider.name == "hash"
    assert provider.dimensions == 384
