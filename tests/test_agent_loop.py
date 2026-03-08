# tests/test_agent_loop.py
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from orchestrator.agent_loop import AgentLoop, TaskResult
from orchestrator.factory import RenderedAgent, ConfirmationGate


def _block(**kwargs):
    """Create a mock content block. SimpleNamespace is used instead of
    MagicMock because ``name`` is a reserved attribute on MagicMock."""
    return SimpleNamespace(**kwargs)


@pytest.fixture
def rendered_agent():
    return RenderedAgent(
        name="Test Agent",
        app_name="TestApp",
        start_url="https://test.example.com/users",
        allowed_url_patterns=["test.example.com"],
        system_prompt="You are a test agent.",
        instructions="Search for user test@example.com and disable them.",
        confirmation_gates=[
            ConfirmationGate(
                action_types=["click_submit", "click_disable"],
                require="teams_approval",
                message_template="About to disable test@example.com",
            )
        ],
        evidence_capture_points=["navigation", "before_confirmation", "after_confirmation", "task_complete", "error"],
        timeout_seconds=60,
        max_steps=10,
    )


@pytest.fixture
def mock_dependencies():
    """Mock all external dependencies for the agent loop."""
    claude = AsyncMock()
    browser_ctrl = AsyncMock()
    evidence = MagicMock()
    approval = AsyncMock()

    browser_ctrl.take_screenshot = AsyncMock(return_value=b"fake-png")
    browser_ctrl.navigate = AsyncMock(return_value={"status": "navigated", "url": "https://test.example.com/users", "title": "Users"})
    browser_ctrl.read_page = AsyncMock(return_value="Users page content")

    evidence.upload_screenshot = MagicMock(return_value={
        "task_id": "test-001",
        "step": 0,
        "action": "navigation",
        "blob_path": "test-001/000_navigation.png",
        "sha256": "abc",
        "timestamp": "20260308T140000Z",
    })

    return {"claude": claude, "browser": browser_ctrl, "evidence": evidence, "approval": approval}


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_simple_task_complete(self, rendered_agent, mock_dependencies):
        """Claude immediately says task_complete -- simplest flow."""
        mock_dependencies["claude"].messages.create = AsyncMock(return_value=MagicMock(
            content=[
                _block(type="tool_use", name="task_complete",
                       input={"summary": "Task done."}, id="tool_1"),
            ],
            stop_reason="end_turn",
        ))

        loop = AgentLoop(
            claude_client=mock_dependencies["claude"],
            browser=mock_dependencies["browser"],
            evidence=mock_dependencies["evidence"],
            approval=mock_dependencies["approval"],
        )

        result = await loop.run(rendered_agent, task_id="test-001")

        assert isinstance(result, TaskResult)
        assert result.success is True
        assert result.summary == "Task done."
        mock_dependencies["evidence"].finalize.assert_called_once_with("test-001")

    @pytest.mark.asyncio
    async def test_max_steps_exceeded(self, rendered_agent, mock_dependencies):
        """Claude keeps emitting tool calls beyond max_steps."""
        rendered_agent.max_steps = 2

        mock_dependencies["claude"].messages.create = AsyncMock(return_value=MagicMock(
            content=[
                _block(type="tool_use", name="navigate",
                       input={"url": "https://test.example.com/users"}, id="tool_1"),
            ],
            stop_reason="tool_use",
        ))

        loop = AgentLoop(
            claude_client=mock_dependencies["claude"],
            browser=mock_dependencies["browser"],
            evidence=mock_dependencies["evidence"],
            approval=mock_dependencies["approval"],
        )

        result = await loop.run(rendered_agent, task_id="test-001")

        assert result.success is False
        assert "max steps" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_builds_correct_initial_messages(self, rendered_agent, mock_dependencies):
        """Verify the first message to Claude includes system prompt and instructions."""
        mock_dependencies["claude"].messages.create = AsyncMock(return_value=MagicMock(
            content=[
                _block(type="tool_use", name="task_complete",
                       input={"summary": "Done"}, id="t1"),
            ],
            stop_reason="end_turn",
        ))

        loop = AgentLoop(
            claude_client=mock_dependencies["claude"],
            browser=mock_dependencies["browser"],
            evidence=mock_dependencies["evidence"],
            approval=mock_dependencies["approval"],
        )

        await loop.run(rendered_agent, task_id="test-001")

        call_kwargs = mock_dependencies["claude"].messages.create.call_args
        assert call_kwargs.kwargs["system"] == "You are a test agent."
        messages = call_kwargs.kwargs["messages"]
        assert "disable them" in str(messages[0])
