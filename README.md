# POC-IAC-AGENTAI

IGA Browser Agent — Python orchestrator using Claude Sonnet 4.6 (Azure AI Foundry) to control a browser via Playwright for Identity Governance and Administration (IGA) CRUD operations against disconnected web applications.

## Features

- **AI-Controlled Browser** — Claude sees screenshots, reasons about the page, decides what to click/type/navigate
- **YAML Agent Factory** — New agents defined as YAML templates, no code changes needed
- **Evidence Pipeline** — Screenshots uploaded to Azure Blob Storage at every step for audit compliance
- **Teams Approval** — Adaptive cards posted to Teams for human-in-the-loop confirmation of write operations
- **Audit Logging** — Full JSON audit trail with SHA-256 hashed screenshots

## Quick Start

```bash
# Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r orchestrator/requirements.txt

# Set required env vars
export FOUNDRY_API_KEY=your-key
export FOUNDRY_RESOURCE=your-resource
export AZURE_STORAGE_CONNECTION_STRING=your-conn-string
export TEAMS_WEBHOOK_URL=your-webhook-url

# Run an agent
python -m orchestrator.main --agent greenfield-deprovision --input user_email=jsmith@example.com
```

## Running Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## API Usage

The agent runs as an HTTP API service in Azure Container Apps.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| GET | /api/agents | List available agent templates |
| POST | /api/tasks | Start a new task |
| GET | /api/tasks/{task_id} | Check task status |
| POST | /approve/{task_id} | Teams approval callback |
| POST | /deny/{task_id} | Teams denial callback |

### Start a task

```bash
curl -X POST https://your-app.azurecontainerapps.io/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "greenfield-provision",
    "inputs": {
      "full_name": "Jane Doe",
      "email": "jdoe@meritage.com",
      "department": "Engineering",
      "title": "Developer",
      "role": "user"
    }
  }'
```

### Check task status

```bash
curl https://your-app.azurecontainerapps.io/api/tasks/{task_id}
```

## Deployment

### Prerequisites

- Azure CLI installed and logged in (`az login`)
- Azure subscription with permissions to create resources
- Azure AI Foundry resource with Claude Sonnet 4.6
- Teams incoming webhook for IGA approvals channel
- Fill in `infrastructure/parameters/dev.bicepparam` with actual values

### First Deploy

```bash
./deploy.sh dev
```

This creates all infrastructure (Storage, Key Vault, ACR, Container Apps) and deploys the agent.

### Redeploy (Code Changes Only)

```bash
./redeploy.sh dev
```

This rebuilds the Docker image and updates the Container App.

### Local Development

```bash
source .venv/bin/activate
python -m orchestrator.main --serve --port 8000
```
