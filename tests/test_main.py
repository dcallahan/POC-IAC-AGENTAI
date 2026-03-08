# tests/test_main.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from types import SimpleNamespace
from orchestrator.main import run_task


def _block(type, name=None, input=None, id=None, text=None):
    return SimpleNamespace(type=type, name=name, input=input, id=id, text=text)


@pytest.mark.asyncio
async def test_run_task_end_to_end(monkeypatch, tmp_path):
    """Integration-level test: verify run_task wires everything together."""
    monkeypatch.setenv("FOUNDRY_API_KEY", "test-key")
    monkeypatch.setenv("FOUNDRY_RESOURCE", "test-resource")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "fake-conn")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://webhook.test")

    agents_dir = str(tmp_path / "agents")
    import os
    os.makedirs(agents_dir)

    # Write a minimal agent YAML
    yaml_content = """
name: "Test Agent"
version: "1.0"
app:
  name: "TestApp"
  start_url: "https://test.example.com"
  allowed_url_patterns: ["test.example.com"]
inputs: []
system_prompt: "You are a test agent."
instructions: "Just complete the task."
confirmation_gates: []
evidence:
  capture_every_step: false
  capture_points: []
timeout_seconds: 60
max_steps: 5
"""
    with open(os.path.join(agents_dir, "test-agent.yaml"), "w") as f:
        f.write(yaml_content)

    with patch("orchestrator.main.async_playwright") as mock_pw, \
         patch("orchestrator.main.anthropic") as mock_anthropic, \
         patch("orchestrator.main.EvidenceCollector") as mock_evidence_cls, \
         patch("orchestrator.main.TeamsApproval") as mock_approval_cls:

        # Mock Playwright
        mock_browser = AsyncMock()
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake-png")
        mock_page.goto = AsyncMock()
        mock_page.title = AsyncMock(return_value="Test Page")
        mock_page.url = "https://test.example.com"
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock Claude — returns task_complete immediately
        # IMPORTANT: Use SimpleNamespace for content blocks, not MagicMock(name=...)
        # because MagicMock reserves the 'name' attribute
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=MagicMock(
            content=[_block(type="tool_use", name="task_complete", input={"summary": "Done"}, id="t1")],
            stop_reason="end_turn",
        ))
        mock_anthropic.Anthropic.return_value = mock_client

        # Mock Evidence
        mock_evidence = MagicMock()
        mock_evidence.upload_screenshot = MagicMock(return_value={
            "task_id": "t", "step": 0, "action": "x", "blob_path": "p", "sha256": "h", "timestamp": "t",
        })
        mock_evidence_cls.return_value = mock_evidence

        result = await run_task(
            agent_name="test-agent",
            inputs={},
            agents_dir=agents_dir,
        )

        assert result.success is True
        assert result.summary == "Done"
