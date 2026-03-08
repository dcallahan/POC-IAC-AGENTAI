"""Evidence pipeline: captures screenshots, uploads to Azure Blob Storage,
and maintains an audit log that is finalized at task completion."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from azure.storage.blob import BlobServiceClient, ContentSettings


class EvidenceCollector:
    def __init__(self, connection_string: str, container_name: str):
        self.blob_service = BlobServiceClient.from_connection_string(connection_string)
        self.container = self.blob_service.get_container_client(container_name)
        self.audit_entries: list[dict] = []

    def upload_screenshot(
        self,
        task_id: str,
        step: int,
        action: str,
        png_bytes: bytes,
    ) -> dict:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        blob_path = f"{task_id}/{timestamp}_{step:03d}_{action}.png"
        sha256 = hashlib.sha256(png_bytes).hexdigest()

        blob_client = self.container.get_blob_client(blob_path)
        blob_client.upload_blob(
            png_bytes,
            overwrite=True,
            content_settings=ContentSettings(content_type="image/png"),
        )

        return {
            "task_id": task_id,
            "step": step,
            "action": action,
            "blob_path": blob_path,
            "sha256": sha256,
            "timestamp": timestamp,
        }

    def log_action(
        self,
        task_id: str,
        step: int,
        operation: str,
        description: str,
        tool_call: str,
        result: str,
        screenshot_blob_path: str,
        screenshot_sha256: str,
        confirmation: dict | None = None,
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id,
            "step": step,
            "operation": operation,
            "description": description,
            "tool_call": tool_call,
            "result": result,
            "screenshot_blob_path": screenshot_blob_path,
            "screenshot_sha256": screenshot_sha256,
        }
        if confirmation:
            entry["confirmation"] = confirmation

        self.audit_entries.append(entry)

    def finalize(self, task_id: str) -> str:
        blob_path = f"{task_id}/audit_log.json"
        blob_client = self.container.get_blob_client(blob_path)

        audit_json = json.dumps(self.audit_entries, indent=2)
        blob_client.upload_blob(
            audit_json,
            overwrite=True,
            content_settings=ContentSettings(content_type="application/json"),
        )

        return blob_path
