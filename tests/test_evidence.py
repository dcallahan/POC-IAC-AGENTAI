# tests/test_evidence.py
import json
import hashlib
import pytest
from unittest.mock import MagicMock, patch, call
from orchestrator.evidence import EvidenceCollector


@pytest.fixture
def mock_blob_service():
    with patch("orchestrator.evidence.BlobServiceClient") as mock_cls:
        service = MagicMock()
        container = MagicMock()
        blob = MagicMock()

        mock_cls.from_connection_string.return_value = service
        service.get_container_client.return_value = container
        container.get_blob_client.return_value = blob

        yield {
            "service_class": mock_cls,
            "service": service,
            "container": container,
            "blob": blob,
        }


class TestEvidenceCollector:
    def test_init_creates_container_client(self, mock_blob_service):
        collector = EvidenceCollector(
            connection_string="fake-conn-string",
            container_name="iga-evidence",
        )
        mock_blob_service["service_class"].from_connection_string.assert_called_once_with("fake-conn-string")
        mock_blob_service["service"].get_container_client.assert_called_once_with("iga-evidence")

    def test_upload_screenshot(self, mock_blob_service):
        collector = EvidenceCollector("fake-conn", "iga-evidence")
        png_bytes = b"fake-screenshot-png"

        record = collector.upload_screenshot(
            task_id="iga-deprov-001",
            step=3,
            action="click_disable",
            png_bytes=png_bytes,
        )

        # Verify blob was uploaded
        mock_blob_service["blob"].upload_blob.assert_called_once()

        # Verify record fields
        assert record["task_id"] == "iga-deprov-001"
        assert record["step"] == 3
        assert record["action"] == "click_disable"
        assert record["sha256"] == hashlib.sha256(png_bytes).hexdigest()
        assert "iga-deprov-001" in record["blob_path"]
        assert record["blob_path"].endswith(".png")

    def test_log_action(self, mock_blob_service):
        collector = EvidenceCollector("fake-conn", "iga-evidence")

        collector.log_action(
            task_id="iga-deprov-001",
            step=3,
            operation="click",
            description="Disable button",
            tool_call="click('Disable button')",
            result="success",
            screenshot_blob_path="iga-evidence/iga-deprov-001/003.png",
            screenshot_sha256="abc123",
        )

        assert len(collector.audit_entries) == 1
        entry = collector.audit_entries[0]
        assert entry["task_id"] == "iga-deprov-001"
        assert entry["step"] == 3
        assert entry["operation"] == "click"
        assert entry["result"] == "success"

    def test_log_action_with_confirmation(self, mock_blob_service):
        collector = EvidenceCollector("fake-conn", "iga-evidence")

        collector.log_action(
            task_id="iga-deprov-001",
            step=5,
            operation="click",
            description="Delete user",
            tool_call="click('Delete')",
            result="success",
            screenshot_blob_path="path.png",
            screenshot_sha256="abc",
            confirmation={"approved_by": "derik@meritage.com", "approved_at": "2026-03-08T14:30:00Z"},
        )

        entry = collector.audit_entries[0]
        assert entry["confirmation"]["approved_by"] == "derik@meritage.com"

    def test_finalize_uploads_audit_log(self, mock_blob_service):
        collector = EvidenceCollector("fake-conn", "iga-evidence")

        collector.log_action(
            task_id="iga-deprov-001", step=1, operation="navigate",
            description="Go to users", tool_call="navigate(url)",
            result="success", screenshot_blob_path="p.png", screenshot_sha256="x",
        )

        collector.finalize("iga-deprov-001")

        # Should upload audit_log.json
        blob_calls = mock_blob_service["container"].get_blob_client.call_args_list
        audit_call = [c for c in blob_calls if "audit_log.json" in str(c)]
        assert len(audit_call) > 0
