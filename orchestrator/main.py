# orchestrator/main.py
"""CLI entry point for the IGA Browser Agent.

Usage:
    python -m orchestrator.main --agent greenfield-deprovision --input user_email=jsmith@meritage.com
    python -m orchestrator.main --agent greenfield-deprovision --input user_email=jsmith@meritage.com --input action=delete
    python -m orchestrator.main --serve --port 8000
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from datetime import datetime, timezone

import anthropic
from playwright.async_api import async_playwright

from orchestrator.agent_loop import AgentLoop, TaskResult
from orchestrator.approval import TeamsApproval
from orchestrator.browser import BrowserController
from orchestrator.config import Config
from orchestrator.evidence import EvidenceCollector
from orchestrator.factory import AgentFactory

logger = logging.getLogger(__name__)


def generate_task_id(agent_name: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    return f"{agent_name}-{ts}-{short_id}"


async def run_task(
    agent_name: str,
    inputs: dict,
    agents_dir: str = "agents",
) -> TaskResult:
    config = Config.from_env()
    task_id = generate_task_id(agent_name)

    logger.info(f"Starting task {task_id} with agent '{agent_name}'")

    # Load agent template
    factory = AgentFactory(agents_dir)
    template = factory.load(agent_name)
    rendered = template.render(**inputs)

    # Initialize Claude client (Foundry endpoint)
    claude_client = anthropic.Anthropic(
        base_url=config.foundry_base_url,
        api_key=config.foundry_api_key,
    )

    # Initialize evidence collector
    evidence = EvidenceCollector(
        connection_string=config.azure_storage_connection_string,
        container_name=config.evidence_container,
    )

    # Initialize Teams approval (None = auto-approve, fully autonomous)
    approval = None
    if config.teams_webhook_url:
        approval = TeamsApproval(
            webhook_url=config.teams_webhook_url,
            callback_host=config.approval_callback_host,
            callback_port=config.approval_callback_port,
            timeout_seconds=config.approval_timeout_seconds,
        )

    # Launch browser and run agent loop
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        browser_ctrl = BrowserController(page, rendered.allowed_url_patterns)

        # Navigate to start URL
        await browser_ctrl.navigate(rendered.start_url)

        loop = AgentLoop(
            claude_client=claude_client,
            browser=browser_ctrl,
            evidence=evidence,
            approval=approval,
        )

        result = await loop.run(rendered, task_id=task_id)

        await browser.close()

    logger.info(f"Task {task_id} completed: success={result.success}, summary={result.summary}")
    return result


def parse_inputs(input_args: list[str]) -> dict:
    inputs = {}
    for arg in input_args:
        key, _, value = arg.partition("=")
        inputs[key.strip()] = value.strip()
    return inputs


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="IGA Browser Agent")
    parser.add_argument("--agent", required=False, help="Name of the agent YAML template (without .yaml)")
    parser.add_argument("--input", action="append", default=[], help="Input as key=value (repeatable)")
    parser.add_argument("--agents-dir", default="agents", help="Directory containing agent YAML files")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode (visible)")
    parser.add_argument("--serve", action="store_true", help="Start API server instead of running a single task")
    parser.add_argument("--port", type=int, default=8000, help="API server port (with --serve)")

    args = parser.parse_args()

    if args.serve:
        import uvicorn
        from orchestrator.api import app
        uvicorn.run(app, host="0.0.0.0", port=args.port)
        return

    if not args.agent:
        parser.error("--agent is required when not using --serve")

    inputs = parse_inputs(args.input)

    result = asyncio.run(run_task(
        agent_name=args.agent,
        inputs=inputs,
        agents_dir=args.agents_dir,
    ))

    if result.success:
        print(f"\nTask {result.task_id} completed successfully")
        print(f"  Summary: {result.summary}")
        print(f"  Steps: {result.steps_taken}")
        if result.audit_blob_path:
            print(f"  Audit log: {result.audit_blob_path}")
    else:
        print(f"\nTask {result.task_id} failed")
        print(f"  Summary: {result.summary}")
        print(f"  Steps: {result.steps_taken}")
        exit(1)


if __name__ == "__main__":
    main()
