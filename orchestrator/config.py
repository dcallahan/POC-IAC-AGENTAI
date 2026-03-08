from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    foundry_api_key: str
    foundry_resource: str
    foundry_model: str
    azure_storage_connection_string: str
    evidence_container: str
    teams_webhook_url: str
    approval_callback_host: str
    approval_callback_port: int
    approval_timeout_seconds: int

    @classmethod
    def from_env(cls) -> Config:
        def require(key: str) -> str:
            val = os.environ.get(key)
            if not val:
                raise ValueError(f"Required environment variable {key} is not set")
            return val

        return cls(
            foundry_api_key=require("FOUNDRY_API_KEY"),
            foundry_resource=require("FOUNDRY_RESOURCE"),
            foundry_model=os.environ.get("FOUNDRY_MODEL", "claude-sonnet-4-6"),
            azure_storage_connection_string=require("AZURE_STORAGE_CONNECTION_STRING"),
            evidence_container=os.environ.get("EVIDENCE_CONTAINER", "iga-evidence"),
            teams_webhook_url=os.environ.get("TEAMS_WEBHOOK_URL", ""),
            approval_callback_host=os.environ.get("APPROVAL_CALLBACK_HOST", "0.0.0.0"),
            approval_callback_port=int(os.environ.get("APPROVAL_CALLBACK_PORT", "8080")),
            approval_timeout_seconds=int(os.environ.get("APPROVAL_TIMEOUT_SECONDS", "300")),
        )

    @property
    def approval_callback_base_url(self) -> str:
        """Base URL for Teams adaptive card callback buttons."""
        fqdn = os.environ.get("CONTAINER_APP_FQDN")
        if fqdn:
            return f"https://{fqdn}"
        return f"http://{self.approval_callback_host}:{self.approval_callback_port}"

    @property
    def foundry_base_url(self) -> str:
        return f"https://{self.foundry_resource}.services.ai.azure.com/anthropic"
