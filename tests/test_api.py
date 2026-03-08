# tests/test_api.py
"""Tests for the FastAPI API layer."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from orchestrator.api import app, _tasks
from orchestrator.approval import pending_approvals


@pytest.fixture(autouse=True)
def clear_tasks():
    """Clear the in-memory task store and pending approvals between tests."""
    _tasks.clear()
    pending_approvals.clear()
    yield
    _tasks.clear()
    pending_approvals.clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"


def test_list_agents_returns_templates(client):
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    names = [a["name"] for a in data]
    assert "greenfield-provision" in names
    # Each entry should have inputs
    for agent in data:
        assert "inputs" in agent


def test_create_task_returns_202(client):
    with patch("orchestrator.api.run_task_background", new_callable=AsyncMock) as mock_run:
        resp = client.post("/api/tasks", json={
            "agent": "greenfield-provision",
            "inputs": {
                "full_name": "Jane Doe",
                "email": "jdoe@example.com",
                "department": "Engineering",
                "title": "Developer",
                "role": "admin",
            },
        })
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "running"
    assert data["agent"] == "greenfield-provision"
    assert "task_id" in data


def test_create_task_validates_agent_exists(client):
    resp = client.post("/api/tasks", json={
        "agent": "nonexistent-agent",
        "inputs": {},
    })
    assert resp.status_code == 404


def test_create_task_validates_inputs(client):
    resp = client.post("/api/tasks", json={
        "agent": "greenfield-provision",
        "inputs": {},
    })
    assert resp.status_code == 422


def test_get_nonexistent_task_returns_404(client):
    resp = client.get("/api/tasks/nonexistent-task-id")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Approval callback endpoint tests
# ---------------------------------------------------------------------------
def test_approve_resolves_pending_future(client):
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    pending_approvals["task-approve-1"] = future

    resp = client.post("/approve/task-approve-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["task_id"] == "task-approve-1"

    # Future should have been resolved
    assert future.done()
    result = future.result()
    assert result.approved is True
    assert result.approver == "teams-user"
    assert result.task_id == "task-approve-1"
    loop.close()


def test_deny_resolves_pending_future(client):
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    pending_approvals["task-deny-1"] = future

    resp = client.post("/deny/task-deny-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "denied"
    assert data["task_id"] == "task-deny-1"

    # Future should have been resolved
    assert future.done()
    result = future.result()
    assert result.approved is False
    assert result.approver == "teams-user"
    loop.close()


def test_approve_unknown_task_returns_ok(client):
    """Approving a task_id with no pending future should still return 200."""
    resp = client.post("/approve/unknown-task")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"


def test_deny_unknown_task_returns_ok(client):
    """Denying a task_id with no pending future should still return 200."""
    resp = client.post("/deny/unknown-task")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "denied"
