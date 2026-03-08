# orchestrator/agent_loop.py
"""Core agentic loop: Claude reasons about screenshots, emits tool calls,
orchestrator executes them via Playwright, captures evidence, and manages
approval gates."""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from orchestrator.browser import BrowserController
from orchestrator.evidence import EvidenceCollector
from orchestrator.approval import TeamsApproval, ApprovalResult
from orchestrator.factory import RenderedAgent
from orchestrator.tools import get_tool_definitions

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    success: bool
    summary: str
    task_id: str
    steps_taken: int = 0
    audit_blob_path: str | None = None


class AgentLoop:
    def __init__(
        self,
        claude_client,
        browser: BrowserController,
        evidence: EvidenceCollector,
        approval: TeamsApproval,
    ):
        self.claude = claude_client
        self.browser = browser
        self.evidence = evidence
        self.approval = approval

    async def run(self, agent: RenderedAgent, task_id: str) -> TaskResult:
        tools = get_tool_definitions()
        messages = []
        step = 0

        # Take initial screenshot
        screenshot_bytes = await self.browser.take_screenshot()
        self.evidence.upload_screenshot(
            task_id=task_id, step=step, action="initial", png_bytes=screenshot_bytes,
        )

        # Build initial user message with instructions + screenshot
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": agent.instructions},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(screenshot_bytes).decode(),
                    },
                },
            ],
        })

        while step < agent.max_steps:
            # Call Claude
            response = await self.claude.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=agent.system_prompt,
                tools=tools,
                messages=messages,
            )

            # Process response content blocks
            assistant_content = response.content
            tool_results = []

            for block in assistant_content:
                if block.type != "tool_use":
                    continue

                step += 1
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                # Handle task_complete
                if tool_name == "task_complete":
                    self._capture_evidence(task_id, step, "task_complete", screenshot_bytes)
                    audit_path = self.evidence.finalize(task_id)
                    return TaskResult(
                        success=True,
                        summary=tool_input["summary"],
                        task_id=task_id,
                        steps_taken=step,
                        audit_blob_path=audit_path,
                    )

                # Handle confirmation requests
                if tool_name == "request_confirmation":
                    approval_result = await self.approval.wait_for_approval(
                        task_id=task_id,
                        action_summary=tool_input["summary"],
                    )
                    if not approval_result.approved:
                        self.evidence.finalize(task_id)
                        return TaskResult(
                            success=False,
                            summary=f"Denied: {tool_input['summary']}",
                            task_id=task_id,
                            steps_taken=step,
                        )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": "Approved. Proceed.",
                    })
                    continue

                # Check confirmation gates from YAML
                confirmation = None
                if self._requires_confirmation(tool_name, agent):
                    gate = self._matching_gate(tool_name, agent)
                    approval_result = await self.approval.wait_for_approval(
                        task_id=task_id,
                        action_summary=gate.message_template if gate else f"{tool_name}: {tool_input}",
                    )
                    if not approval_result.approved:
                        self.evidence.finalize(task_id)
                        return TaskResult(
                            success=False,
                            summary=f"Denied at step {step}",
                            task_id=task_id,
                            steps_taken=step,
                        )
                    confirmation = {
                        "approved_by": approval_result.approver,
                        "approved_at": approval_result.timestamp,
                    }

                # Execute browser action
                result = await self._execute_tool(tool_name, tool_input)

                # Capture evidence
                screenshot_bytes = await self.browser.take_screenshot()
                screenshot_record = self.evidence.upload_screenshot(
                    task_id=task_id, step=step, action=tool_name, png_bytes=screenshot_bytes,
                )

                self.evidence.log_action(
                    task_id=task_id,
                    step=step,
                    operation=tool_name,
                    description=str(tool_input),
                    tool_call=f"{tool_name}({tool_input})",
                    result="success",
                    screenshot_blob_path=screenshot_record["blob_path"],
                    screenshot_sha256=screenshot_record["sha256"],
                    confirmation=confirmation,
                )

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": [
                        {"type": "text", "text": str(result)},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64.b64encode(screenshot_bytes).decode(),
                            },
                        },
                    ],
                })

            # Add assistant message and tool results to conversation
            messages.append({"role": "assistant", "content": assistant_content})
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            # If Claude stopped without tool use, task is done
            if response.stop_reason == "end_turn" and not tool_results:
                text_content = " ".join(
                    b.text for b in assistant_content if hasattr(b, "text")
                )
                self.evidence.finalize(task_id)
                return TaskResult(
                    success=True,
                    summary=text_content or "Task completed",
                    task_id=task_id,
                    steps_taken=step,
                )

        # Max steps exceeded
        self.evidence.finalize(task_id)
        return TaskResult(
            success=False,
            summary=f"Max steps exceeded ({agent.max_steps})",
            task_id=task_id,
            steps_taken=step,
        )

    async def _execute_tool(self, name: str, input: dict) -> dict:
        if name == "navigate":
            return await self.browser.navigate(input["url"])
        elif name == "click":
            return await self.browser.click(input["description"])
        elif name == "type_text":
            return await self.browser.type_text(input["description"], input["text"])
        elif name == "select_option":
            return await self.browser.select_option(input["description"], input["value"])
        elif name == "scroll":
            return await self.browser.scroll(input["direction"])
        elif name == "screenshot":
            await self.browser.take_screenshot()
            return {"status": "screenshot_taken"}
        elif name == "read_page":
            text = await self.browser.read_page()
            return {"status": "read", "text": text}
        else:
            return {"status": "unknown_tool", "name": name}

    def _requires_confirmation(self, tool_name: str, agent: RenderedAgent) -> bool:
        for gate in agent.confirmation_gates:
            if tool_name in gate.action_types:
                return True
        return False

    def _matching_gate(self, tool_name: str, agent: RenderedAgent):
        for gate in agent.confirmation_gates:
            if tool_name in gate.action_types:
                return gate
        return None

    def _capture_evidence(self, task_id: str, step: int, action: str, png_bytes: bytes) -> None:
        self.evidence.upload_screenshot(
            task_id=task_id, step=step, action=action, png_bytes=png_bytes,
        )
