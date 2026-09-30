import json

import pytest

from iot_diagnosis.ingestion import ingest_text
from iot_diagnosis.repository import DiagnosisRepository


def test_tags_survive_reopen_and_reingestion(tmp_path):
    path = str(tmp_path / "knowledge.db")
    repository = DiagnosisRepository(path)
    ingest_text(
        repository,
        source="device_docs",
        document_id="ota-manual",
        title="OTA Guide",
        content="# Upgrade\n\n" + "Upgrade the firmware safely. " * 100,
        device_type="MODEL-X",
        category="software",
        document_type="manual",
        hardware_version="Rev. B",
        firmware_version="2.0",
        chunk_size=64,
        overlap=8,
    )
    repository = DiagnosisRepository(path)
    item = next(
        doc
        for doc in repository.list_knowledge_documents()["items"]
        if doc["document_id"] == "ota-manual"
    )
    assert item["category"] == "software"
    assert item["document_type"] == "manual"
    assert item["hardware_version"] == "Rev. B"
    assert item["firmware_version"] == "2.0"
    assert item["device_type"] == "MODEL-X"
    assert item["chunk_count"] > 1
    for row in repository.knowledge_documents(["device_docs"]):
        if row["document_id"] == "ota-manual":
            metadata = json.loads(row["metadata_json"])
            assert metadata["metadata"]["category"] == "software"
            assert "heading_path" in metadata
    ingest_text(
        repository,
        source="device_docs",
        document_id="ota-manual",
        title="OTA v3",
        content="Updated firmware guide.",
        device_type=None,
        category="software",
        firmware_version="3.0",
    )
    item = next(
        doc
        for doc in repository.list_knowledge_documents()["items"]
        if doc["document_id"] == "ota-manual"
    )
    assert item["firmware_version"] == "3.0"
    assert item.get("hardware_version") is None
    assert item["device_type"] is None


def test_existing_sources_and_curated_documents_are_classified_without_rewriting(tmp_path):
    repository = DiagnosisRepository(str(tmp_path / "knowledge.db"))
    for source, document_id in (
        ("sensor_docs", "sensor-manual"),
        ("device_docs", "hardware-manual"),
        ("device_docs", "ESP_HTTPS_OTA_GUIDE"),
    ):
        repository.replace_knowledge_document(
            source=source,
            document_id=document_id,
            title=document_id,
            chunks=["content"],
            device_type=None,
        )
    before = repository.knowledge_documents(["device_docs", "sensor_docs"])
    docs = {doc["document_id"]: doc for doc in repository.list_knowledge_documents()["items"]}
    assert docs["sensor-manual"]["category"] == docs["hardware-manual"]["category"] == "hardware"
    assert docs["ESP_HTTPS_OTA_GUIDE"]["category"] == "software"
    assert docs["ESP_HTTPS_OTA_GUIDE"]["document_type"] == "manual"
    assert docs["MQTT_DOC_03"]["category"] == "protocol"
    assert repository.knowledge_documents(["device_docs", "sensor_docs"]) == before


@pytest.mark.parametrize(
    "tags", [{"category": "unknown"}, {"document_type": "unknown"}, {"hardware_version": "x" * 121}]
)
def test_invalid_tags_are_rejected_before_writes(tmp_path, tags):
    repository = DiagnosisRepository(str(tmp_path / "knowledge.db"))
    with pytest.raises(ValueError):
        ingest_text(
            repository,
            source="device_docs",
            document_id="invalid",
            title="Invalid",
            content="content",
            **tags,
        )
    assert not any(
        doc["document_id"] == "invalid" for doc in repository.list_knowledge_documents()["items"]
    )
