import os
import pytest
from orchestrator.config import Config


def test_config_loads_from_env(monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "test-key-123")
    monkeypatch.setenv("FOUNDRY_RESOURCE", "meritage-iga-agent")
    monkeypatch.setenv("FOUNDRY_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "DefaultEndpointsProtocol=https;AccountName=test")
    monkeypatch.setenv("EVIDENCE_CONTAINER", "iga-evidence")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://outlook.office.com/webhook/test")
    monkeypatch.setenv("APPROVAL_CALLBACK_HOST", "0.0.0.0")
    monkeypatch.setenv("APPROVAL_CALLBACK_PORT", "8765")
    monkeypatch.setenv("APPROVAL_TIMEOUT_SECONDS", "300")

    config = Config.from_env()

    assert config.foundry_api_key == "test-key-123"
    assert config.foundry_resource == "meritage-iga-agent"
    assert config.foundry_model == "claude-sonnet-4-6"
    assert config.azure_storage_connection_string == "DefaultEndpointsProtocol=https;AccountName=test"
    assert config.evidence_container == "iga-evidence"
    assert config.teams_webhook_url == "https://outlook.office.com/webhook/test"
    assert config.approval_callback_host == "0.0.0.0"
    assert config.approval_callback_port == 8765
    assert config.approval_timeout_seconds == 300


def test_config_defaults(monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "test-key")
    monkeypatch.setenv("FOUNDRY_RESOURCE", "test-resource")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "conn-string")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://webhook.test")

    config = Config.from_env()

    assert config.foundry_model == "claude-sonnet-4-6"
    assert config.evidence_container == "iga-evidence"
    assert config.approval_callback_host == "0.0.0.0"
    assert config.approval_callback_port == 8080
    assert config.approval_timeout_seconds == 300


def test_config_missing_required_raises(monkeypatch):
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.delenv("FOUNDRY_RESOURCE", raising=False)

    with pytest.raises(ValueError, match="FOUNDRY_API_KEY"):
        Config.from_env()
