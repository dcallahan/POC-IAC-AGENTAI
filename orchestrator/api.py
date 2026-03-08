# orchestrator/api.py
"""FastAPI HTTP API layer wrapping the IGA Browser Agent orchestrator."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from orchestrator.approval import ApprovalResult, pending_approvals
from orchestrator.factory import AgentFactory, ValidationError
from orchestrator.main import generate_task_id, run_task

logger = logging.getLogger(__name__)

AGENTS_DIR = "agents"

app = FastAPI(title="IGA Browser Agent API", version="1.0.0")

# ---------------------------------------------------------------------------
# In-memory task store
# ---------------------------------------------------------------------------
_tasks: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class TaskRequest(BaseModel):
    agent: str
    inputs: dict[str, Any] = {}


class TaskResponse(BaseModel):
    task_id: str
    status: str
    agent: str


class TaskStatus(BaseModel):
    task_id: str
    status: str
    agent: str
    result: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------
async def run_task_background(task_id: str, agent_name: str, inputs: dict) -> None:
    """Run an agent task and update the in-memory task store on completion."""
    try:
        result = await run_task(
            agent_name=agent_name,
            inputs=inputs,
            agents_dir=AGENTS_DIR,
        )
        _tasks[task_id]["status"] = "completed" if result.success else "failed"
        _tasks[task_id]["result"] = {
            "success": result.success,
            "summary": result.summary,
            "steps_taken": result.steps_taken,
            "audit_blob_path": result.audit_blob_path,
        }
    except Exception as exc:
        logger.exception(f"Task {task_id} raised an exception")
        _tasks[task_id]["status"] = "failed"
        _tasks[task_id]["result"] = {"success": False, "summary": str(exc)}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/api/agents")
async def list_agents():
    factory = AgentFactory(AGENTS_DIR)
    agent_names = factory.list()
    agents = []
    for name in agent_names:
        template = factory.load(name)
        agents.append({
            "name": name,
            "inputs": [
                {
                    "name": inp.name,
                    "type": inp.type,
                    "required": inp.required,
                    "default": inp.default,
                    "values": inp.values,
                }
                for inp in template.inputs
            ],
        })
    return agents


@app.post("/api/tasks", status_code=202)
async def create_task(req: TaskRequest, background_tasks: BackgroundTasks):
    factory = AgentFactory(AGENTS_DIR)

    # Validate agent exists
    try:
        template = factory.load(req.agent)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent '{req.agent}' not found")

    # Validate inputs against template
    try:
        template.render(**req.inputs)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    task_id = generate_task_id(req.agent)

    _tasks[task_id] = {
        "task_id": task_id,
        "status": "running",
        "agent": req.agent,
        "result": None,
    }

    background_tasks.add_task(run_task_background, task_id, req.agent, req.inputs)

    return TaskResponse(task_id=task_id, status="running", agent=req.agent)


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    entry = _tasks[task_id]
    return TaskStatus(
        task_id=entry["task_id"],
        status=entry["status"],
        agent=entry["agent"],
        result=entry["result"],
    )


# ---------------------------------------------------------------------------
# Approval callback endpoints
# ---------------------------------------------------------------------------
@app.post("/approve/{task_id}")
async def approve_task(task_id: str):
    if task_id in pending_approvals:
        pending_approvals[task_id].set_result(
            ApprovalResult(approved=True, approver="teams-user", task_id=task_id)
        )
    return {"status": "approved", "task_id": task_id}


@app.post("/deny/{task_id}")
async def deny_task(task_id: str):
    if task_id in pending_approvals:
        pending_approvals[task_id].set_result(
            ApprovalResult(approved=False, approver="teams-user", task_id=task_id)
        )
    return {"status": "denied", "task_id": task_id}
