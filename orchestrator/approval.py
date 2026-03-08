"""Teams approval flow via incoming webhook and adaptive cards.

Posts an adaptive card to a Teams channel with Approve/Deny buttons.
Buttons callback to the FastAPI server running in the orchestrator.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone

import aiohttp

# Module-level dict shared with FastAPI callback routes
pending_approvals: dict[str, asyncio.Future] = {}


@dataclass
class ApprovalResult:
    approved: bool
    approver: str | None
    task_id: str
    timed_out: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TeamsApproval:
    def __init__(
        self,
        webhook_url: str,
        callback_host: str,
        callback_port: int,
        timeout_seconds: int = 300,
    ):
        self.webhook_url = webhook_url
        self.callback_host = callback_host
        self.callback_port = callback_port
        self.timeout_seconds = timeout_seconds

    def build_adaptive_card(
        self,
        task_id: str,
        action_summary: str,
        callback_base_url: str | None = None,
    ) -> dict:
        base = callback_base_url or f"http://{self.callback_host}:{self.callback_port}"
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": "IGA Agent — Confirmation Required",
                                "weight": "Bolder",
                                "size": "Medium",
                            },
                            {
                                "type": "TextBlock",
                                "text": f"**Task:** {task_id}",
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": f"**Action:** {action_summary}",
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": "Do you approve this action?",
                                "wrap": True,
                            },
                        ],
                        "actions": [
                            {
                                "type": "Action.Http",
                                "title": "Approve",
                                "method": "POST",
                                "url": f"{base}/approve/{task_id}",
                                "style": "positive",
                            },
                            {
                                "type": "Action.Http",
                                "title": "Deny",
                                "method": "POST",
                                "url": f"{base}/deny/{task_id}",
                                "style": "destructive",
                            },
                        ],
                    },
                }
            ],
        }

    async def send_card(self, task_id: str, action_summary: str) -> None:
        card = self.build_adaptive_card(task_id, action_summary)
        async with aiohttp.ClientSession() as session:
            await session.post(
                self.webhook_url,
                json=card,
                headers={"Content-Type": "application/json"},
            )

    async def wait_for_approval(self, task_id: str, action_summary: str) -> ApprovalResult:
        """Send adaptive card and wait for callback response."""
        future: asyncio.Future[ApprovalResult] = asyncio.get_event_loop().create_future()
        pending_approvals[task_id] = future

        # Send the card
        await self.send_card(task_id, action_summary)

        # Wait for response or timeout
        try:
            result = await asyncio.wait_for(future, timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            result = ApprovalResult(
                approved=False, approver=None, task_id=task_id, timed_out=True
            )
        finally:
            pending_approvals.pop(task_id, None)

        return result
