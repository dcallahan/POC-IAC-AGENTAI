# tests/test_approval.py
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from orchestrator.approval import TeamsApproval, ApprovalResult


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
