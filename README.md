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
