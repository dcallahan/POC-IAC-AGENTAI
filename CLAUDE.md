# POC-IAC-AGENTAI — IGA Browser Agent

## Project Overview

Python orchestrator using Claude Sonnet 4.6 (Azure AI Foundry) as an intelligent browser controller for IGA CRUD operations against disconnected web applications. YAML-defined agent templates (factory model). Evidence screenshots uploaded to Azure Blob Storage. Teams approval for write operations.

## Directory Structure

```
├── orchestrator/         # Python orchestrator modules
│   ├── main.py           # CLI entry point
│   ├── agent_loop.py     # Core agentic loop (Claude ⇄ Browser)
│   ├── browser.py        # Playwright wrapper with NL locators
│   ├── evidence.py       # Blob upload + audit logging
│   ├── approval.py       # Teams webhook + callback server
│   ├── factory.py        # YAML loader + template renderer
│   ├── tools.py          # Tool definitions for Claude
│   └── config.py         # Settings from env vars
├── agents/               # YAML agent templates (one per task type)
├── infrastructure/       # Bicep IaC (storage, key vault)
├── tests/                # Unit and integration tests
└── docs/plans/           # Design documents
```

## Development Conventions

- **Runtime:** Python 3.11+
- **Tests:** `source .venv/bin/activate && python -m pytest tests/ -v`
- **New agent:** Create a YAML file in `agents/` — no Python code changes needed
- **Secrets:** Use environment variables. Never hardcode.
- **Infrastructure:** Bicep modules in `infrastructure/modules/`, orchestrated by `main.bicep`
- **Formatting:** Follow PEP 8

## Required Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FOUNDRY_API_KEY` | Yes | — | Azure AI Foundry API key |
| `FOUNDRY_RESOURCE` | Yes | — | Foundry resource name |
| `FOUNDRY_MODEL` | No | `claude-sonnet-4-6` | Model to use |
| `AZURE_STORAGE_CONNECTION_STRING` | Yes | — | Storage account for evidence |
| `EVIDENCE_CONTAINER` | No | `iga-evidence` | Blob container name |
| `TEAMS_WEBHOOK_URL` | Yes | — | Teams incoming webhook URL |
| `APPROVAL_CALLBACK_HOST` | No | `0.0.0.0` | Callback server bind host |
| `APPROVAL_CALLBACK_PORT` | No | `8080` | Callback server port |
| `APPROVAL_TIMEOUT_SECONDS` | No | `300` | Approval timeout |

## Git & PR Workflow

- **Branch strategy:** Feature branches off `main`, PRs for all changes
- **When to create a PR:**
  - After completing a logical group of tasks (e.g., all orchestrator modules)
  - After adding a new agent adapter (YAML template + any supporting changes)
  - After infrastructure changes (Bicep modules)
  - Before merging any work into `main`
- **PR format:**
  - Title: Short, descriptive (under 70 chars)
  - Body: Summary bullets + test plan
  - All tests must pass before merge
- **Commits:** Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`)
- **Never push directly to `main`** — always use PRs

## Running

```bash
python -m orchestrator.main --agent greenfield-deprovision --input user_email=jsmith@meritage.com
```
