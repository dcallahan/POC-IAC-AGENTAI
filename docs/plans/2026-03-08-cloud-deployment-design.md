# IGA Browser Agent — Cloud Deployment Design

**Date:** 2026-03-08
**Author:** Derik
**Status:** Draft
**Extends:** `2026-03-08-iga-browser-agent-design.md`

---

## 1. Summary

Extend the IGA Browser Agent from a local CLI tool to a cloud-hosted API service running in Azure Container Apps. The agent is triggered via HTTP API (Postman, webhooks, or any client), runs Playwright + Chromium inside a container, and is deployed as a single package via Bicep + ACR.

## 2. What Changes

| Aspect | Before (Local) | After (Cloud) |
|--------|----------------|---------------|
| **Entry point** | CLI (`python -m orchestrator.main`) | HTTP API (`POST /api/tasks`) |
| **Browser** | Local Playwright + Chromium | Container-hosted Playwright + Chromium |
| **Deployment** | Manual `python` on dev machine | `az deployment` + `az acr build` + Container Apps auto-pull |
| **Trigger** | Human runs CLI command | Any HTTP client (Postman, webhook, automation) |
| **Approval callback** | `localhost:8080` | Container App FQDN (public ingress) |
| **Infrastructure** | Storage + Key Vault | + ACR + Log Analytics + Container Apps Environment + Container App |

**What does NOT change:** Orchestrator modules (agent_loop.py, browser.py, evidence.py, factory.py, tools.py), YAML agent templates, existing Bicep modules (storage, keyvault, budget).

## 3. Architecture

```
                        ┌─────────────────────────────────┐
                        │     Any HTTP Client              │
                        │  Postman / Webhook / Automation  │
                        └──────────────┬──────────────────┘
                                       │ HTTPS
                                       ▼
┌──────────────────────────────────────────────────────────────────┐
│  Azure Container Apps (aca-iga-agent-dev)                        │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Docker Container (Python 3.11 + Playwright + Chromium)    │  │
│  │                                                            │  │
│  │  ┌──────────────┐  ┌────────────────────────────────────┐  │  │
│  │  │ FastAPI       │  │ Orchestrator (existing code)       │  │  │
│  │  │               │  │                                    │  │  │
│  │  │ POST /tasks   │──│ AgentLoop + BrowserController      │  │  │
│  │  │ GET /tasks/id │  │ EvidenceCollector + TeamsApproval   │  │  │
│  │  │ GET /health   │  │ AgentFactory (YAML templates)      │  │  │
│  │  │ GET /agents   │  │                                    │  │  │
│  │  └──────────────┘  └────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────┘  │
│  Container Apps Environment (cae-iga-agent-dev)                  │
│  Log Analytics Workspace (log-iga-agent-dev)                     │
└──────────────────────────────────────────────────────────────────┘
         │                    │                    │
         │ Anthropic SDK      │ Blob SDK           │ HTTP POST
         ▼                    ▼                    ▼
┌──────────────┐  ┌───────────────────┐  ┌─────────────────┐
│ Azure AI      │  │ Storage Account   │  │ Teams Channel   │
│ Foundry       │  │ (stigaagentdev)   │  │ Incoming Webhook│
│ Claude 4.6    │  │ iga-evidence/     │  │ Adaptive Cards  │
└──────────────┘  └───────────────────┘  └─────────────────┘
                           │
                  ┌────────┴────────┐
                  │ Key Vault        │
                  │ (kv-iga-agent)   │
                  │ FOUNDRY_API_KEY  │
                  │ TEAMS_WEBHOOK    │
                  │ STORAGE_CONN_STR │
                  └─────────────────┘

┌────────────────────┐
│ Container Registry  │
│ (acrigaagentdev)    │
│ iga-agent:latest    │
└────────────────────┘
```

## 4. API Design

### POST /api/tasks — Start a task

```json
// Request
{
  "agent": "greenfield-provision",
  "inputs": {
    "full_name": "John Smith",
    "email": "jsmith@meritage.com",
    "department": "Engineering",
    "title": "Developer",
    "role": "user"
  }
}

// Response (202 Accepted)
{
  "task_id": "greenfield-provision-20260308143022-a1b2c3",
  "status": "running",
  "agent": "greenfield-provision"
}
```

### GET /api/tasks/{task_id} — Check task status

```json
// Response (200)
{
  "task_id": "greenfield-provision-20260308143022-a1b2c3",
  "status": "complete",        // running | complete | failed | awaiting_approval
  "success": true,
  "summary": "User John Smith created with role 'user'",
  "steps_taken": 8,
  "audit_blob_path": "greenfield-provision-20260308.../audit_log.json",
  "started_at": "2026-03-08T14:30:22Z",
  "completed_at": "2026-03-08T14:32:45Z"
}
```

### GET /api/agents — List available agents

```json
// Response (200)
{
  "agents": [
    {
      "name": "greenfield-provision",
      "display_name": "Greenfield.AI User Provisioning",
      "inputs": [
        {"name": "full_name", "type": "string", "required": true},
        {"name": "email", "type": "string", "required": true}
      ]
    }
  ]
}
```

### GET /health — Health check

```json
{"status": "healthy", "version": "1.0.0"}
```

## 5. Task Lifecycle

```
POST /api/tasks
    │
    ├── Validate inputs against YAML schema
    ├── Generate task_id
    ├── Store task in in-memory dict (status: running)
    ├── Spawn asyncio.create_task(run_task(...))
    └── Return 202 { task_id, status: "running" }

Background task:
    ├── Launch Playwright browser
    ├── Run AgentLoop (existing code, unchanged)
    │   ├── Screenshot → Claude → Tool calls → Execute
    │   ├── Evidence uploaded to Blob at each step
    │   └── Teams approval if confirmation gate hit
    ├── On complete: update task dict (status: complete/failed)
    └── Close browser

GET /api/tasks/{task_id}
    └── Return current task state from in-memory dict
```

**Task state is in-memory for v1.** Tasks are lost on container restart. This is acceptable for a POC — the evidence and audit logs are persisted in Blob Storage regardless.

## 6. Container Image

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app
COPY orchestrator/ orchestrator/
COPY agents/ agents/
COPY orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

EXPOSE 8000
CMD ["uvicorn", "orchestrator.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

Key decisions:
- **Base image:** Microsoft's official Playwright Python image (includes browser dependencies)
- **Port 8000:** FastAPI/uvicorn default, Container Apps ingress routes to this
- **Agents baked in:** YAML templates are part of the image. New agents = rebuild + redeploy (acceptable for POC, could mount as volume later)

## 7. Azure Infrastructure (New Resources)

| Resource | Bicep Module | Naming | Purpose |
|----------|-------------|--------|---------|
| **Container Registry** | `modules/acr.bicep` | `acrigaagent{env}` | Store Docker images |
| **Log Analytics Workspace** | `modules/loganalytics.bicep` | `log-iga-agent-{env}` | Container Apps logging (required) |
| **Container Apps Environment** | `modules/containerapp-env.bicep` | `cae-iga-agent-{env}` | Networking + logging for Container Apps |
| **Container App** | `modules/containerapp.bicep` | `aca-iga-agent-{env}` | The running container with HTTP ingress |

### Existing (unchanged)
| Resource | Module | Purpose |
|----------|--------|---------|
| Storage Account | `modules/storage.bicep` | Evidence blob storage |
| Key Vault | `modules/keyvault.bicep` | Secrets |
| Budget | `modules/budget.bicep` | Cost alerts |

### Container App Configuration

```
Container App:
  image: acrigaagent{env}.azurecr.io/iga-agent:latest
  cpu: 1.0
  memory: 2.0Gi          # Chromium needs ~1GB
  min_replicas: 0         # Scale to zero when idle
  max_replicas: 3         # Max 3 concurrent tasks
  ingress:
    external: true        # Public HTTPS endpoint
    target_port: 8000
    transport: http
  env:
    FOUNDRY_API_KEY:                  → Key Vault secret ref
    FOUNDRY_RESOURCE:                 → parameter
    AZURE_STORAGE_CONNECTION_STRING:  → Key Vault secret ref
    TEAMS_WEBHOOK_URL:                → Key Vault secret ref
    APPROVAL_CALLBACK_HOST:           → Container App FQDN (auto-resolved)
```

## 8. Approval Callback in Cloud

The current approval.py starts a callback server on `localhost:8080`. In the cloud:

- The Container App has a public FQDN: `aca-iga-agent-dev.{random}.{region}.azurecontainerapps.io`
- The approval callback routes (`/approve/{task_id}`, `/deny/{task_id}`) are served by FastAPI on the same port as the API
- No separate callback server needed — FastAPI handles both API requests and Teams callbacks
- The adaptive card's action URLs point to the Container App's FQDN

**Change:** Move approval callback routes into FastAPI app. TeamsApproval class no longer starts its own HTTP server — it just builds cards and waits on a Future that the FastAPI route resolves.

## 9. Deploy as One Package

```bash
# One-command deploy script: deploy.sh

# 1. Deploy infrastructure (creates ACR, Container Apps, etc.)
az deployment group create \
  --resource-group rg-iga-agent-dev \
  --template-file infrastructure/main.bicep \
  --parameters infrastructure/parameters/dev.bicepparam

# 2. Build and push Docker image to ACR
az acr build \
  --registry acrigaagentdev \
  --image iga-agent:latest \
  .

# 3. Update Container App to use new image (auto if using ACR pull)
az containerapp update \
  --name aca-iga-agent-dev \
  --resource-group rg-iga-agent-dev \
  --image acrigaagentdev.azurecr.io/iga-agent:latest
```

**Redeploy on changes:** Just re-run step 2 + 3. Infrastructure only needs step 1 if Bicep changes.

## 10. Environment Variables (Updated)

| Variable | Required | Source | Description |
|----------|----------|--------|-------------|
| `FOUNDRY_API_KEY` | Yes | Key Vault → Container App env | Azure AI Foundry API key |
| `FOUNDRY_RESOURCE` | Yes | Bicep parameter | Foundry resource name |
| `FOUNDRY_MODEL` | No | Default: `claude-sonnet-4-6` | Model to use |
| `AZURE_STORAGE_CONNECTION_STRING` | Yes | Key Vault → Container App env | Storage account |
| `EVIDENCE_CONTAINER` | No | Default: `iga-evidence` | Blob container name |
| `TEAMS_WEBHOOK_URL` | Yes | Key Vault → Container App env | Teams incoming webhook |
| `APPROVAL_CALLBACK_HOST` | No | Auto: Container App FQDN | For adaptive card URLs |
| `APPROVAL_CALLBACK_PORT` | No | Default: `8000` | Same port as FastAPI |
| `PORT` | No | Default: `8000` | Container App sets this |

## 11. Scope Boundaries

### In Scope (This Update)
- FastAPI API layer (POST /tasks, GET /tasks/{id}, GET /agents, GET /health)
- Dockerfile with Playwright + Chromium
- Bicep modules for ACR, Log Analytics, Container Apps Environment, Container App
- Updated main.bicep orchestrating all resources
- Deploy script (build + push + deploy)
- Approval callback integrated into FastAPI
- In-memory task state management

### Out of Scope (Future)
- Persistent task state (Table Storage or Redis)
- Authentication on API endpoints (API key, Entra ID)
- Auto-scaling based on queue depth
- Blue/green deployments
- CI/CD pipeline (GitHub Actions)
- Volume-mounted agent templates (dynamic without rebuild)
- WebSocket for real-time task progress
