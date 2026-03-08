# tests/test_approval.py
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from orchestrator.approval import TeamsApproval, ApprovalResult, pending_approvals


@pytest.fixture(autouse=True)
def clear_pending():
    """Clear pending_approvals between tests."""
    pending_approvals.clear()
    yield
    pending_approvals.clear()


class TestTeamsApproval:
    def test_build_adaptive_card(self):
        approval = TeamsApproval(
            webhook_url="https://outlook.office.com/webhook/test",
            callback_host="localhost",
            callback_port=8765,
            timeout_seconds=60,
        )

        card = approval.build_adaptive_card(
            task_id="iga-deprov-001",
            action_summary="Disable user jsmith@meritage.com in Greenfield.AI",
        )

        card_json = json.dumps(card)
        assert "iga-deprov-001" in card_json
        assert "jsmith@meritage.com" in card_json
        assert "Approve" in card_json
        assert "Deny" in card_json
        assert "8765" in card_json  # callback port in action URLs

    def test_build_adaptive_card_with_callback_base_url(self):
        approval = TeamsApproval(
            webhook_url="https://outlook.office.com/webhook/test",
            callback_host="localhost",
            callback_port=8765,
        )

        card = approval.build_adaptive_card(
            task_id="iga-deprov-001",
            action_summary="Disable user jsmith",
            callback_base_url="https://myapp.eastus.azurecontainerapps.io",
        )

        card_json = json.dumps(card)
        assert "https://myapp.eastus.azurecontainerapps.io/approve/iga-deprov-001" in card_json
        assert "https://myapp.eastus.azurecontainerapps.io/deny/iga-deprov-001" in card_json
        # Should NOT contain the default host/port
        assert "8765" not in card_json

    @pytest.mark.asyncio
    async def test_send_card_posts_to_webhook(self):
        approval = TeamsApproval(
            webhook_url="https://outlook.office.com/webhook/test",
            callback_host="localhost",
            callback_port=8765,
            timeout_seconds=5,
        )

        with patch("orchestrator.approval.aiohttp.ClientSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_session.post = AsyncMock(return_value=mock_resp)

            await approval.send_card(
                task_id="iga-deprov-001",
                action_summary="Disable user jsmith",
            )

            mock_session.post.assert_called_once()
            call_args = mock_session.post.call_args
            assert call_args[0][0] == "https://outlook.office.com/webhook/test"

    @pytest.mark.asyncio
    async def test_wait_for_approval_registers_future(self):
        approval = TeamsApproval(
            webhook_url="https://outlook.office.com/webhook/test",
            callback_host="localhost",
            callback_port=8765,
            timeout_seconds=5,
        )

        with patch.object(approval, "send_card", new_callable=AsyncMock) as mock_send:
            # Simulate an approval coming in after send_card is called
            async def resolve_future(*args, **kwargs):
                # The future should be registered by now
                assert "iga-deprov-002" in pending_approvals
                pending_approvals["iga-deprov-002"].set_result(
                    ApprovalResult(approved=True, approver="derik", task_id="iga-deprov-002")
                )

            mock_send.side_effect = resolve_future

            result = await approval.wait_for_approval(
                task_id="iga-deprov-002",
                action_summary="Disable user jsmith",
            )

            assert result.approved is True
            assert result.approver == "derik"
            assert result.task_id == "iga-deprov-002"
            # Future should be cleaned up
            assert "iga-deprov-002" not in pending_approvals

    @pytest.mark.asyncio
    async def test_wait_for_approval_timeout(self):
        approval = TeamsApproval(
            webhook_url="https://outlook.office.com/webhook/test",
            callback_host="localhost",
            callback_port=8765,
            timeout_seconds=0.1,  # Very short timeout for test
        )

        with patch.object(approval, "send_card", new_callable=AsyncMock):
            result = await approval.wait_for_approval(
                task_id="iga-deprov-003",
                action_summary="Disable user jsmith",
            )

            assert result.approved is False
            assert result.timed_out is True
            assert result.task_id == "iga-deprov-003"
            # Future should be cleaned up
            assert "iga-deprov-003" not in pending_approvals

    def test_approval_result_approved(self):
        result = ApprovalResult(
            approved=True,
            approver="derik@meritage.com",
            task_id="iga-deprov-001",
        )
        assert result.approved is True
        assert result.approver == "derik@meritage.com"

    def test_approval_result_timeout(self):
        result = ApprovalResult(
            approved=False,
            approver=None,
            task_id="iga-deprov-001",
            timed_out=True,
        )
        assert result.approved is False
        assert result.timed_out is True
