# tests/test_integration.py
"""Integration smoke test: verifies the full pipeline wires together correctly.
All external services (Foundry, Playwright, Azure Blob) are mocked."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from orchestrator.main import run_task


def _block(type, name=None, input=None, id=None, text=None):
    """Helper to create mock content blocks. Uses SimpleNamespace because
    MagicMock reserves the 'name' attribute."""
    return SimpleNamespace(type=type, name=name, input=input, id=id, text=text)


@pytest.fixture
def env_vars(monkeypatch, tmp_path):
    monkeypatch.setenv("FOUNDRY_API_KEY", "test-key")
    monkeypatch.setenv("FOUNDRY_RESOURCE", "test-resource")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "fake-conn")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://webhook.test")

    agents_dir = str(tmp_path / "agents")
    os.makedirs(agents_dir)
    with open(os.path.join(agents_dir, "smoke-test.yaml"), "w") as f:
        f.write("""
name: "Smoke Test"
version: "1.0"
app:
  name: "TestApp"
  start_url: "https://test.example.com"
  allowed_url_patterns: ["test.example.com"]
inputs:
  - name: user_email
    type: string
    required: true
system_prompt: "You are a test agent."
instructions: "Find user {{ user_email }} and report their status."
confirmation_gates: []
evidence:
  capture_every_step: false
  capture_points:
    - "on": task_complete
timeout_seconds: 60
max_steps: 10
""")
    return agents_dir


@pytest.mark.asyncio
async def test_smoke_navigate_then_complete(env_vars):
    """Claude navigates to start URL, reads page, then completes."""
    agents_dir = env_vars
    call_count = 0

    async def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: Claude reads the page
            return MagicMock(
                content=[_block(type="tool_use", name="read_page", input={}, id="t1")],
                stop_reason="tool_use",
            )
        else:
            # Second call: Claude completes
            return MagicMock(
                content=[_block(
                    type="tool_use", name="task_complete",
                    input={"summary": "User jsmith is active with role Admin."}, id="t2",
                )],
                stop_reason="end_turn",
            )

    with patch("orchestrator.main.async_playwright") as mock_pw, \
         patch("orchestrator.main.anthropic") as mock_anthropic, \
         patch("orchestrator.main.EvidenceCollector") as mock_ev_cls, \
         patch("orchestrator.main.TeamsApproval"):

        # Playwright mocks
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"png-bytes")
        mock_page.goto = AsyncMock()
        mock_page.title = AsyncMock(return_value="Users")
        mock_page.url = "https://test.example.com"
        mock_page.evaluate = AsyncMock(return_value="User: jsmith, Role: Admin, Status: Active")
        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_pw_ctx = AsyncMock()
        mock_pw_ctx.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw_ctx)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

        # Claude mock
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=mock_create)
        mock_anthropic.Anthropic.return_value = mock_client

        # Evidence mock
        mock_ev = MagicMock()
        mock_ev.upload_screenshot = MagicMock(return_value={
            "task_id": "t", "step": 0, "action": "x",
            "blob_path": "p.png", "sha256": "h", "timestamp": "t",
        })
        mock_ev_cls.return_value = mock_ev

        result = await run_task(
            agent_name="smoke-test",
            inputs={"user_email": "jsmith@meritage.com"},
            agents_dir=agents_dir,
        )

        assert result.success is True
        assert "jsmith" in result.summary
        assert result.steps_taken == 2
        assert mock_client.messages.create.call_count == 2
        mock_ev.finalize.assert_called_once()
