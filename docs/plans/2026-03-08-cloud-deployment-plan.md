# Cloud Deployment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy the IGA Browser Agent as a containerized API service in Azure Container Apps, callable via HTTP from any client.

**Architecture:** FastAPI wraps the existing orchestrator. Docker image includes Playwright + Chromium. Bicep deploys ACR + Container Apps + supporting infrastructure. Single deploy script for build + push + update.

**Tech Stack:** FastAPI, uvicorn, Docker, Azure Container Apps, Azure Container Registry, Bicep

---

## Phase 1: API Layer (FastAPI)

Add an HTTP API that wraps the existing CLI orchestrator. No Docker or Azure changes yet — runs locally for testing.

### Task 1.1: Add FastAPI dependency and API skeleton

**Files:**
- Modify: `orchestrator/requirements.txt`
- Create: `orchestrator/api.py`
- Create: `tests/test_api.py`

**Step 1: Add dependencies to requirements.txt**

Add to `orchestrator/requirements.txt`:
```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
```

**Step 2: Write the failing test**

```python
# tests/test_api.py
"""Tests for the FastAPI API layer."""
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from fastapi.testclient import TestClient


def _make_app():
    """Import app fresh to avoid module-level side effects."""
    from orchestrator.api import app
    return app


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestListAgents:
    def test_list_agents_returns_templates(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert isinstance(data["agents"], list)
        # Should find our YAML templates
        names = [a["name"] for a in data["agents"]]
        assert "greenfield-provision" in names


class TestCreateTask:
    @patch("orchestrator.api.run_task_background")
    def test_create_task_returns_202(self, mock_run):
        mock_run.return_value = None
        app = _make_app()
        client = TestClient(app)
        resp = client.post("/api/tasks", json={
            "agent": "greenfield-provision",
            "inputs": {
                "full_name": "Test User",
                "email": "test@example.com",
                "department": "IT",
                "title": "Tester",
                "role": "user",
            },
        })
        assert resp.status_code == 202
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "running"
        assert data["agent"] == "greenfield-provision"

    @patch("orchestrator.api.run_task_background")
    def test_create_task_validates_agent_exists(self, mock_run):
        app = _make_app()
        client = TestClient(app)
        resp = client.post("/api/tasks", json={
            "agent": "nonexistent-agent",
            "inputs": {},
        })
        assert resp.status_code == 404

    @patch("orchestrator.api.run_task_background")
    def test_create_task_validates_inputs(self, mock_run):
        app = _make_app()
        client = TestClient(app)
        resp = client.post("/api/tasks", json={
            "agent": "greenfield-provision",
            "inputs": {},  # Missing required inputs
        })
        assert resp.status_code == 422


class TestGetTask:
    def test_get_nonexistent_task_returns_404(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/api/tasks/nonexistent-id")
        assert resp.status_code == 404
```

**Step 3: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_api.py -v`
Expected: FAIL (orchestrator.api does not exist)

**Step 4: Write the API module**

```python
# orchestrator/api.py
"""FastAPI API layer for the IGA Browser Agent.

Wraps the existing orchestrator with HTTP endpoints:
- POST /api/tasks — Start a new task (async, returns task_id)
- GET /api/tasks/{task_id} — Get task status and result
- GET /api/agents — List available agent templates
- GET /health — Health check
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

from orchestrator.factory import AgentFactory, ValidationError
from orchestrator.main import generate_task_id, run_task

logger = logging.getLogger(__name__)

app = FastAPI(title="IGA Browser Agent", version="1.0.0")

# In-memory task state (lost on restart — evidence persists in Blob)
_tasks: dict[str, dict[str, Any]] = {}

AGENTS_DIR = "agents"


# --- Request/Response models ---

class TaskRequest(BaseModel):
    agent: str
    inputs: dict[str, str] = {}


class TaskResponse(BaseModel):
    task_id: str
    status: str
    agent: str


class TaskStatus(BaseModel):
    task_id: str
    status: str  # running | complete | failed | awaiting_approval
    agent: str
    success: bool | None = None
    summary: str | None = None
    steps_taken: int | None = None
    audit_blob_path: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


# --- Background task runner ---

async def run_task_background(task_id: str, agent_name: str, inputs: dict):
    """Run the agent task and update in-memory state on completion."""
    try:
        _tasks[task_id]["status"] = "running"
        result = await run_task(
            agent_name=agent_name,
            inputs=inputs,
            agents_dir=AGENTS_DIR,
        )
        _tasks[task_id].update({
            "status": "complete" if result.success else "failed",
            "success": result.success,
            "summary": result.summary,
            "steps_taken": result.steps_taken,
            "audit_blob_path": result.audit_blob_path,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.exception(f"Task {task_id} failed with error")
        _tasks[task_id].update({
            "status": "failed",
            "success": False,
            "summary": str(e),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })


# --- Endpoints ---

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
            "display_name": template.name,
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
    return {"agents": agents}


@app.post("/api/tasks", status_code=202)
async def create_task(req: TaskRequest, background_tasks: BackgroundTasks):
    # Validate agent exists
    factory = AgentFactory(AGENTS_DIR)
    try:
        template = factory.load(req.agent)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent '{req.agent}' not found")

    # Validate inputs against template
    try:
        template.render(**req.inputs)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Generate task ID and store initial state
    task_id = generate_task_id(req.agent)
    _tasks[task_id] = {
        "task_id": task_id,
        "status": "running",
        "agent": req.agent,
        "success": None,
        "summary": None,
        "steps_taken": None,
        "audit_blob_path": None,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }

    # Run task in background
    background_tasks.add_task(run_task_background, task_id, req.agent, req.inputs)

    return TaskResponse(task_id=task_id, status="running", agent=req.agent)


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return _tasks[task_id]
```

**Step 5: Run tests**

Run: `source .venv/bin/activate && pip install fastapi uvicorn[standard] httpx && python -m pytest tests/test_api.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add orchestrator/api.py orchestrator/requirements.txt tests/test_api.py
git commit -m "feat: add FastAPI API layer wrapping orchestrator"
```

---

### Task 1.2: Integrate approval callbacks into FastAPI

**Files:**
- Modify: `orchestrator/api.py`
- Modify: `orchestrator/approval.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_approval.py`

**Step 1: Write the failing test**

Add to `tests/test_api.py`:
```python
class TestApprovalCallbacks:
    def test_approve_callback_returns_200(self):
        from orchestrator.api import app, _pending_approvals
        import asyncio
        # Set up a pending future
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        _pending_approvals["test-task-123"] = future
        client = TestClient(app)
        resp = client.post("/approve/test-task-123")
        assert resp.status_code == 200
        loop.close()

    def test_deny_callback_returns_200(self):
        from orchestrator.api import app, _pending_approvals
        import asyncio
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        _pending_approvals["test-task-456"] = future
        client = TestClient(app)
        resp = client.post("/deny/test-task-456")
        assert resp.status_code == 200
        loop.close()
```

**Step 2: Update approval.py to use shared pending dict**

Modify `orchestrator/approval.py`:
- Remove `_start_callback_server()`, `_handle_approve()`, `_handle_deny()` methods
- `wait_for_approval()` no longer starts its own HTTP server
- Instead, it registers a Future in a shared dict and sends the card, then awaits the Future
- The FastAPI routes (`/approve/{task_id}`, `/deny/{task_id}`) resolve the Future

Add a module-level dict:
```python
# Shared pending approvals dict — FastAPI routes resolve these Futures
pending_approvals: dict[str, asyncio.Future] = {}
```

TeamsApproval.wait_for_approval becomes:
```python
async def wait_for_approval(self, task_id: str, action_summary: str) -> ApprovalResult:
    future = asyncio.get_event_loop().create_future()
    pending_approvals[task_id] = future
    await self.send_card(task_id, action_summary)
    try:
        result = await asyncio.wait_for(future, timeout=self.timeout_seconds)
    except asyncio.TimeoutError:
        result = ApprovalResult(approved=False, approver=None, task_id=task_id, timed_out=True)
    finally:
        pending_approvals.pop(task_id, None)
    return result
```

**Step 3: Add callback routes to api.py**

```python
from orchestrator.approval import pending_approvals, ApprovalResult

_pending_approvals = pending_approvals  # re-export for test access

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
```

**Step 4: Update config.py**

The `APPROVAL_CALLBACK_HOST` should now default to the Container App FQDN when set, or fall back to the value from the `CONTAINER_APP_FQDN` environment variable (which Azure Container Apps provides automatically via the `CONTAINER_APP_NAME` + revision metadata).

Add to config.py:
```python
@property
def approval_callback_base_url(self) -> str:
    """Base URL for Teams adaptive card callback buttons."""
    fqdn = os.environ.get("CONTAINER_APP_FQDN")
    if fqdn:
        return f"https://{fqdn}"
    return f"http://{self.approval_callback_host}:{self.approval_callback_port}"
```

Update TeamsApproval to use this instead of constructing its own URL.

**Step 5: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_api.py tests/test_approval.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add orchestrator/api.py orchestrator/approval.py orchestrator/config.py tests/test_api.py tests/test_approval.py
git commit -m "feat: integrate approval callbacks into FastAPI, remove standalone server"
```

---

### Task 1.3: Update main.py to support both CLI and API modes

**Files:**
- Modify: `orchestrator/main.py`

**Step 1: Add --serve flag**

Add a `--serve` flag to main.py that starts the FastAPI server instead of running a single task:

```python
parser.add_argument("--serve", action="store_true", help="Start API server instead of running a single task")
parser.add_argument("--port", type=int, default=8000, help="API server port (with --serve)")
```

When `--serve` is set:
```python
if args.serve:
    import uvicorn
    from orchestrator.api import app
    uvicorn.run(app, host="0.0.0.0", port=args.port)
```

**Step 2: Run existing tests (ensure CLI still works)**

Run: `source .venv/bin/activate && python -m pytest tests/test_main.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add orchestrator/main.py
git commit -m "feat: add --serve flag to main.py for API server mode"
```

---

## Phase 2: Containerization

### Task 2.1: Create Dockerfile

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

**Step 1: Write the Dockerfile**

```dockerfile
# Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

# Install Python dependencies
COPY orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium for Playwright
RUN playwright install chromium

# Copy application code
COPY orchestrator/ orchestrator/
COPY agents/ agents/
COPY pyproject.toml .

# Default port for FastAPI
ENV PORT=8000
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start API server
CMD ["python", "-m", "uvicorn", "orchestrator.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: Write .dockerignore**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.git/
.gitignore
docs/
tests/
infrastructure/
*.md
.env
evidence/
firebase-debug.log
```

**Step 3: Verify Docker build**

Run: `docker build -t iga-agent:local .`
Expected: Builds successfully

**Step 4: Verify container runs**

Run: `docker run --rm -p 8000:8000 -e FOUNDRY_API_KEY=test -e FOUNDRY_RESOURCE=test -e AZURE_STORAGE_CONNECTION_STRING=test -e TEAMS_WEBHOOK_URL=test iga-agent:local`

Verify: `curl http://localhost:8000/health` returns `{"status":"healthy","version":"1.0.0"}`

**Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: add Dockerfile with Playwright + Chromium for Container Apps"
```

---

## Phase 3: Azure Infrastructure (Bicep)

### Task 3.1: Log Analytics Workspace module

**Files:**
- Create: `infrastructure/modules/loganalytics.bicep`

**Step 1: Write the module**

```bicep
// infrastructure/modules/loganalytics.bicep
@description('Name of the Log Analytics workspace')
param workspaceName string

@description('Location')
param location string = resourceGroup().location

@description('Retention in days')
param retentionInDays int = 30

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionInDays
  }
}

output workspaceId string = workspace.id
output workspaceName string = workspace.name
output customerId string = workspace.properties.customerId
output sharedKey string = workspace.listKeys().primarySharedKey
```

**Step 2: Validate**

Run: `az bicep build --file infrastructure/modules/loganalytics.bicep`
Expected: No errors

**Step 3: Commit**

```bash
git add infrastructure/modules/loganalytics.bicep
git commit -m "feat: add Log Analytics workspace Bicep module"
```

---

### Task 3.2: Azure Container Registry module

**Files:**
- Create: `infrastructure/modules/acr.bicep`

**Step 1: Write the module**

```bicep
// infrastructure/modules/acr.bicep
@description('Name of the Container Registry (must be globally unique, alphanumeric)')
param registryName string

@description('Location')
param location string = resourceGroup().location

@description('SKU for the registry')
@allowed(['Basic', 'Standard', 'Premium'])
param sku string = 'Basic'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  sku: {
    name: sku
  }
  properties: {
    adminUserEnabled: true  // Needed for Container Apps to pull images
  }
}

output registryId string = acr.id
output registryName string = acr.name
output loginServer string = acr.properties.loginServer
output adminUsername string = acr.listCredentials().username
output adminPassword string = acr.listCredentials().passwords[0].value
```

**Step 2: Validate**

Run: `az bicep build --file infrastructure/modules/acr.bicep`
Expected: No errors

**Step 3: Commit**

```bash
git add infrastructure/modules/acr.bicep
git commit -m "feat: add Azure Container Registry Bicep module"
```

---

### Task 3.3: Container Apps Environment module

**Files:**
- Create: `infrastructure/modules/containerapp-env.bicep`

**Step 1: Write the module**

```bicep
// infrastructure/modules/containerapp-env.bicep
@description('Name of the Container Apps Environment')
param environmentName string

@description('Location')
param location string = resourceGroup().location

@description('Log Analytics workspace customer ID')
param logAnalyticsCustomerId string

@description('Log Analytics workspace shared key')
@secure()
param logAnalyticsSharedKey string

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
  }
}

output environmentId string = environment.id
output environmentName string = environment.name
output defaultDomain string = environment.properties.defaultDomain
```

**Step 2: Validate**

Run: `az bicep build --file infrastructure/modules/containerapp-env.bicep`
Expected: No errors

**Step 3: Commit**

```bash
git add infrastructure/modules/containerapp-env.bicep
git commit -m "feat: add Container Apps Environment Bicep module"
```

---

### Task 3.4: Container App module

**Files:**
- Create: `infrastructure/modules/containerapp.bicep`

**Step 1: Write the module**

```bicep
// infrastructure/modules/containerapp.bicep
@description('Name of the Container App')
param containerAppName string

@description('Location')
param location string = resourceGroup().location

@description('Container Apps Environment ID')
param environmentId string

@description('ACR login server (e.g. myacr.azurecr.io)')
param acrLoginServer string

@description('ACR admin username')
param acrUsername string

@description('ACR admin password')
@secure()
param acrPassword string

@description('Container image name:tag')
param imageName string = 'iga-agent:latest'

@description('CPU cores (e.g. 1.0)')
param cpu string = '1.0'

@description('Memory (e.g. 2.0Gi)')
param memory string = '2.0Gi'

@description('Minimum replicas (0 = scale to zero)')
param minReplicas int = 0

@description('Maximum replicas')
param maxReplicas int = 3

@description('Azure AI Foundry resource name')
param foundryResource string

@description('Key Vault URI for secret references')
param keyVaultUri string

@description('Storage connection string')
@secure()
param storageConnectionString string

@description('Foundry API key')
@secure()
param foundryApiKey string

@description('Teams webhook URL')
@secure()
param teamsWebhookUrl string

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      registries: [
        {
          server: acrLoginServer
          username: acrUsername
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acrPassword
        }
        {
          name: 'foundry-api-key'
          value: foundryApiKey
        }
        {
          name: 'storage-connection-string'
          value: storageConnectionString
        }
        {
          name: 'teams-webhook-url'
          value: teamsWebhookUrl
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'iga-agent'
          image: '${acrLoginServer}/${imageName}'
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            {
              name: 'FOUNDRY_API_KEY'
              secretRef: 'foundry-api-key'
            }
            {
              name: 'FOUNDRY_RESOURCE'
              value: foundryResource
            }
            {
              name: 'AZURE_STORAGE_CONNECTION_STRING'
              secretRef: 'storage-connection-string'
            }
            {
              name: 'TEAMS_WEBHOOK_URL'
              secretRef: 'teams-webhook-url'
            }
            {
              name: 'PORT'
              value: '8000'
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '3'
              }
            }
          }
        ]
      }
    }
  }
}

output containerAppId string = containerApp.id
output containerAppName string = containerApp.name
output fqdn string = containerApp.properties.configuration.ingress.fqdn
output latestRevisionFqdn string = containerApp.properties.latestRevisionFqdn
```

**Step 2: Validate**

Run: `az bicep build --file infrastructure/modules/containerapp.bicep`
Expected: No errors

**Step 3: Commit**

```bash
git add infrastructure/modules/containerapp.bicep
git commit -m "feat: add Container App Bicep module with secrets and scaling"
```

---

### Task 3.5: Update main.bicep to orchestrate all modules

**Files:**
- Modify: `infrastructure/main.bicep`
- Modify: `infrastructure/parameters/dev.bicepparam`

**Step 1: Update main.bicep**

Add parameters for the new resources and wire all modules together:

```bicep
// New parameters
@description('Azure AI Foundry resource name')
param foundryResource string

@secure()
@description('Azure AI Foundry API key')
param foundryApiKey string

@secure()
@description('Teams incoming webhook URL')
param teamsWebhookUrl string

@description('Container image tag')
param imageTag string = 'latest'
```

Add new modules after existing storage/keyvault/budget:

```bicep
module loganalytics 'modules/loganalytics.bicep' = {
  name: 'loganalytics-${nameSuffix}'
  params: {
    workspaceName: 'log-${nameSuffix}'
    location: location
  }
}

module acr 'modules/acr.bicep' = {
  name: 'acr-${nameSuffix}'
  params: {
    registryName: replace('acr${nameSuffix}', '-', '')
    location: location
  }
}

module containerAppEnv 'modules/containerapp-env.bicep' = {
  name: 'cae-${nameSuffix}'
  params: {
    environmentName: 'cae-${nameSuffix}'
    location: location
    logAnalyticsCustomerId: loganalytics.outputs.customerId
    logAnalyticsSharedKey: loganalytics.outputs.sharedKey
  }
}

module containerApp 'modules/containerapp.bicep' = {
  name: 'aca-${nameSuffix}'
  params: {
    containerAppName: 'aca-${nameSuffix}'
    location: location
    environmentId: containerAppEnv.outputs.environmentId
    acrLoginServer: acr.outputs.loginServer
    acrUsername: acr.outputs.adminUsername
    acrPassword: acr.outputs.adminPassword
    imageName: 'iga-agent:${imageTag}'
    foundryResource: foundryResource
    foundryApiKey: foundryApiKey
    storageConnectionString: storage.outputs.connectionString
    teamsWebhookUrl: teamsWebhookUrl
  }
}
```

Add new outputs:
```bicep
output acrLoginServer string = acr.outputs.loginServer
output containerAppFqdn string = containerApp.outputs.fqdn
output containerAppUrl string = 'https://${containerApp.outputs.fqdn}'
```

**Step 2: Update dev.bicepparam**

Add new required parameters (placeholder values):
```
param foundryResource = ''    // Fill: your AI Foundry resource name
param foundryApiKey = ''      // Fill: your Foundry API key
param teamsWebhookUrl = ''    // Fill: your Teams webhook URL
```

**Step 3: Validate**

Run: `az bicep build --file infrastructure/main.bicep`
Expected: No errors

**Step 4: Commit**

```bash
git add infrastructure/main.bicep infrastructure/parameters/dev.bicepparam
git commit -m "feat: update main.bicep with ACR, Log Analytics, Container Apps"
```

---

## Phase 4: Deployment Script & Documentation

### Task 4.1: Create deployment script

**Files:**
- Create: `deploy.sh`

**Step 1: Write the script**

```bash
#!/usr/bin/env bash
# deploy.sh — Build, push, and deploy the IGA Browser Agent
# Usage: ./deploy.sh [dev|prod]
set -euo pipefail

ENV="${1:-dev}"
RG="rg-iga-agent-${ENV}"
LOCATION="eastus2"

echo "=== IGA Browser Agent — Deploy to ${ENV} ==="

# Step 1: Create resource group if it doesn't exist
echo "[1/4] Ensuring resource group ${RG}..."
az group create --name "$RG" --location "$LOCATION" --output none 2>/dev/null || true

# Step 2: Deploy infrastructure
echo "[2/4] Deploying infrastructure (Bicep)..."
DEPLOY_OUTPUT=$(az deployment group create \
  --resource-group "$RG" \
  --template-file infrastructure/main.bicep \
  --parameters "infrastructure/parameters/${ENV}.bicepparam" \
  --query 'properties.outputs' \
  --output json)

ACR_LOGIN_SERVER=$(echo "$DEPLOY_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['acrLoginServer']['value'])")
APP_URL=$(echo "$DEPLOY_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['containerAppUrl']['value'])")
ACR_NAME=$(echo "$ACR_LOGIN_SERVER" | cut -d. -f1)

echo "  ACR: ${ACR_LOGIN_SERVER}"
echo "  App URL: ${APP_URL}"

# Step 3: Build and push Docker image to ACR
echo "[3/4] Building and pushing Docker image..."
az acr build \
  --registry "$ACR_NAME" \
  --image "iga-agent:latest" \
  --image "iga-agent:$(date +%Y%m%d%H%M%S)" \
  .

# Step 4: Update container app to pull latest image
echo "[4/4] Updating Container App..."
az containerapp update \
  --name "aca-iga-agent-${ENV}" \
  --resource-group "$RG" \
  --image "${ACR_LOGIN_SERVER}/iga-agent:latest"

echo ""
echo "=== Deployment complete ==="
echo "API URL: ${APP_URL}"
echo "Health:  ${APP_URL}/health"
echo "Agents:  ${APP_URL}/api/agents"
echo ""
echo "Test with:"
echo "  curl ${APP_URL}/health"
echo "  curl -X POST ${APP_URL}/api/tasks -H 'Content-Type: application/json' -d '{\"agent\":\"greenfield-provision\",\"inputs\":{\"full_name\":\"Test User\",\"email\":\"test@example.com\",\"department\":\"IT\",\"title\":\"Tester\",\"role\":\"user\"}}'"
```

**Step 2: Make executable**

Run: `chmod +x deploy.sh`

**Step 3: Commit**

```bash
git add deploy.sh
git commit -m "feat: add deploy.sh for one-command build and deploy"
```

---

### Task 4.2: Create redeploy script (code changes only)

**Files:**
- Create: `redeploy.sh`

**Step 1: Write the script**

```bash
#!/usr/bin/env bash
# redeploy.sh — Rebuild and redeploy after code changes (no infra changes)
# Usage: ./redeploy.sh [dev|prod]
set -euo pipefail

ENV="${1:-dev}"
RG="rg-iga-agent-${ENV}"
ACR_NAME="acrigaagent${ENV}"
ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"
TAG="$(date +%Y%m%d%H%M%S)"

echo "=== IGA Browser Agent — Redeploy (${ENV}) ==="

# Build and push new image
echo "[1/2] Building image (tag: ${TAG})..."
az acr build \
  --registry "$ACR_NAME" \
  --image "iga-agent:latest" \
  --image "iga-agent:${TAG}" \
  .

# Update container app
echo "[2/2] Updating Container App..."
az containerapp update \
  --name "aca-iga-agent-${ENV}" \
  --resource-group "$RG" \
  --image "${ACR_LOGIN_SERVER}/iga-agent:latest"

FQDN=$(az containerapp show \
  --name "aca-iga-agent-${ENV}" \
  --resource-group "$RG" \
  --query 'properties.configuration.ingress.fqdn' \
  --output tsv)

echo ""
echo "=== Redeployed ==="
echo "API: https://${FQDN}"
echo "Tag: ${TAG}"
```

**Step 2: Make executable and commit**

```bash
chmod +x redeploy.sh
git add redeploy.sh
git commit -m "feat: add redeploy.sh for quick code-only redeployments"
```

---

### Task 4.3: Update CLAUDE.md and README.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

**Step 1: Update CLAUDE.md**

Add to the project overview section:
- Document the API endpoints
- Document the deploy/redeploy workflow
- Add Container Apps to the infrastructure section
- Update env vars table

**Step 2: Update README.md**

Add:
- API usage section (curl examples for all endpoints)
- Deployment section (prerequisites, first deploy, redeploy)
- Architecture diagram reference

**Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: update project documentation for cloud deployment"
```

---

### Task 4.4: Update architecture diagram

**Files:**
- Modify: `docs/architecture.mmd`

**Step 1: Update the Mermaid diagram**

Add the new components:
- Azure Container Registry
- Container Apps Environment
- Container App
- FastAPI API layer
- HTTP client (Postman) as the entry point
- Replace CLI operator with HTTP API caller

**Step 2: Regenerate PDF and PNG**

Run: `mmdc -i docs/architecture.mmd -o docs/architecture.png -w 1600 -H 1200`
Run: `mmdc -i docs/architecture.mmd -o docs/architecture.pdf -w 1600 -H 1200`

**Step 3: Commit**

```bash
git add docs/architecture.mmd docs/architecture.png docs/architecture.pdf
git commit -m "docs: update architecture diagram for cloud deployment"
```

---

## Phase Summary

| Phase | Tasks | What It Delivers |
|-------|-------|-----------------|
| **Phase 1: API Layer** | 1.1–1.3 | FastAPI endpoints, approval integration, CLI+API dual mode |
| **Phase 2: Containerization** | 2.1 | Dockerfile, .dockerignore, local container testing |
| **Phase 3: Azure Infrastructure** | 3.1–3.5 | Bicep modules for ACR, Log Analytics, Container Apps Env, Container App, updated orchestrator |
| **Phase 4: Deployment** | 4.1–4.4 | deploy.sh, redeploy.sh, updated docs + diagram |

## Deploy Workflow

**First deploy (new environment):**
```bash
./deploy.sh dev
```
This runs: create resource group → deploy Bicep (all infra) → build Docker image → push to ACR → create Container App

**Code changes (redeploy):**
```bash
./redeploy.sh dev
```
This runs: build Docker image → push to ACR → update Container App

**Infrastructure changes:**
```bash
az deployment group create \
  --resource-group rg-iga-agent-dev \
  --template-file infrastructure/main.bicep \
  --parameters infrastructure/parameters/dev.bicepparam
```
Then `./redeploy.sh dev` if code also changed.

## Prerequisites

Before first deploy:
1. Azure CLI installed and logged in (`az login`)
2. Azure subscription with permissions to create resources
3. Docker installed locally (only needed for local testing — ACR builds in cloud)
4. Azure AI Foundry resource provisioned with Claude Sonnet 4.6
5. Teams incoming webhook configured for IGA approvals channel
6. Fill in `infrastructure/parameters/dev.bicepparam` with actual values
