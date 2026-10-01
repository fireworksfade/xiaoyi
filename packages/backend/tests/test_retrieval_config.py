from app.config import Settings


def test_shared_connections_and_specific_memory_overrides(monkeypatch):
    values = {
        "RETRIEVAL_QDRANT_URL": "http://shared-qdrant:6333",
        "RETRIEVAL_EMBEDDING_BASE_URL": "http://shared-model/v1",
        "RETRIEVAL_EMBEDDING_MODEL": "shared-model",
        "RETRIEVAL_EMBEDDING_API_KEY": "test-key",
        "RETRIEVAL_EMBEDDING_DIMENSIONS": "256",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    for suffix in (
        "QDRANT_URL",
        "EMBEDDING_URL",
        "EMBEDDING_MODEL",
        "EMBEDDING_API_KEY",
        "EMBEDDING_DIMENSIONS",
    ):
        monkeypatch.delenv(f"MEMORY_{suffix}", raising=False)
    settings = Settings(_env_file=None)
    assert settings.memory_qdrant_url == values["RETRIEVAL_QDRANT_URL"]
    assert settings.memory_embedding_url == values["RETRIEVAL_EMBEDDING_BASE_URL"]
    assert settings.memory_embedding_model == "shared-model"
    assert settings.memory_embedding_api_key == "test-key"
    assert settings.memory_embedding_dimensions == 256

    monkeypatch.setenv("MEMORY_EMBEDDING_URL", "")
    monkeypatch.setenv("MEMORY_EMBEDDING_MODEL", "memory-model")
    monkeypatch.setenv("MEMORY_EMBEDDING_DIMENSIONS", "512")
    settings = Settings(_env_file=None)
    assert settings.memory_embedding_url == ""  # Explicit disable beats shared connection.
    assert settings.memory_embedding_model == "memory-model"
    assert settings.memory_embedding_dimensions == 512


def test_python_configuration_field_names_remain_supported():
    settings = Settings(
        _env_file=None, memory_embedding_url="http://local-model", memory_embedding_dimensions=128
    )
    assert settings.memory_embedding_url == "http://local-model"
    assert settings.memory_embedding_dimensions == 128
