# crow

Agent coordination and monitoring system. The "brain" that orchestrates devbot, pilot, erdo, and other agentic systems.

## Architecture

Server/worker model:
- **Server** (FastAPI): holds agent definitions, knowledge (PARA in pgvector), conversations, job queue. Gateways (iMessage, HTTP API) feed inbound messages. Web dashboard for auth, agent management, and API keys.
- **Workers**: poll server for jobs, execute agent runs (Claude API calls), report results.
- **PA agent**: top-level agent that routes all inbound messages to specialist agents.

**One database, local and prod.** Railway Postgres (provisioned via scaffold) is the single source of truth. Local dev and prod hit the same DB — no docker-compose, no local Postgres, no migration drift.

## Tech stack

- Python 3.11+, async-first
- FastAPI + uvicorn (server)
- asyncpg + pgvector (database — Railway Postgres)
- Anthropic SDK (Claude API)
- PyJWT (session tokens)
- Typer (CLI), Rich (output)
- Pydantic + pydantic-settings (config/models)
- Jinja2 (prompt templates + web dashboard)
- watchdog (iMessage FSEvents gateway)

## Install

Published as `crow-agents` on PyPI (the `crow` name was taken). CLI command is still `crow`.

```bash
pip install crow-agents          # from PyPI
pip install git+https://github.com/erdoai/crow.git  # from source
```

## Commands

```bash
crow init                       # bootstrap new project (crow.yml, .env, agents/)
crow serve                      # start server
crow worker                     # start worker (polls server for jobs)
crow message <agent> "text"     # send a test message
crow status                     # system status
crow jobs                       # list jobs

# Agent management
crow agents sync ./agents       # sync local agent .md files to server
crow agents export ./agents     # export all agents from server as .md files

# MCP servers
crow mcp add NAME URL           # add MCP server
crow mcp list                   # list MCP servers
crow mcp remove NAME            # remove MCP server
```

## Using crow in another project

No need to clone this repo. Install and init:

```bash
pip install crow-agents
crow init                          # creates crow.yml, .env, agents/
# edit .env — set CROW_DATABASE_URL and CROW_ANTHROPIC_API_KEY
crow serve                         # start server on :8100
crow worker                        # start worker in another terminal
crow agents sync ./agents          # push your agent .md files to server
```

`crow init` generates:
- **`crow.yml`** — config template with agents, MCP, and auth sections
- **`.env`** — with auto-generated secrets (SESSION_SECRET, CROW_API_KEY, CROW_WORKER_API_KEY). You fill in CROW_DATABASE_URL and CROW_ANTHROPIC_API_KEY.
- **`.gitignore`** — ensures .env is not committed
- **`agents/hello.md`** — sample agent to get started

## Development (contributing to crow itself)

```bash
git clone https://github.com/erdoai/crow.git
cd crow
pip install -e ".[dev]"         # install with dev deps
# Set CROW_DATABASE_URL to your Railway Postgres URL (from scaffold)
crow serve                      # start server on :8100
crow worker                     # start worker in another terminal
ruff check .                    # lint
pytest                          # test
```

## Publishing

Package is `crow-agents` on PyPI. Publishing happens automatically via GitHub Actions when a release is created. The workflow uses PyPI trusted publishing (no API token needed).

## Deployment

Infrastructure provisioned via [scaffold](https://github.com/erdoai/scaffold) ([docs](docs/scaffold-plan.md)):
```bash
scaffold up             # provisions Railway Postgres + server + worker, pushes config
scaffold dev            # runs crow locally, same Railway DB
railway up -d -s <id>   # deploy code changes to Railway
```

## Config

Three config files:
- **`crow.yml`**: agent definitions, MCP servers, auth settings, custom dashboard views. Secrets use `${VAR}` syntax resolved from environment at runtime.
- **`scaffold.config.yml`**: declares required API keys, auto-generated secrets, and optional config. Scaffold reads this during `scaffold up` to prompt for missing keys and auto-generate secrets into `.scaffold/.env`.
- **Environment variables** with `CROW_` prefix: database URL, API keys, port. See `.env.example`.

In production, `crow.yml` is delivered via the `CROW_CONFIG` env var (set by scaffold from the local file via `${{file:crow.yml}}`). The loader checks `CROW_CONFIG` first, falls back to the file.

### MCP servers

Configured in `crow.yml` under the `mcp:` section. Each server has a URL and optional headers (for API key auth). Any MCP server with an HTTP endpoint works — tools are discovered automatically at runtime.

### Auth

Auth is optional, configured in the `auth` section of `crow.yml`:
```yaml
auth:
  enabled: true                     # false = single-user, no login
  session_secret: ${SESSION_SECRET}
  api_key: ${CROW_API_KEY}          # static API key (when auth disabled)
  resend:
    api_key: ${RESEND_API_KEY}      # email OTP via Resend
    from: ${RESEND_FROM}             # defaults to "crow <noreply@erdo.ai>"
```

When enabled: email OTP sign-in → onboarding ("what should I call you?") → dashboard with per-user conversations, knowledge, phone links, API keys. When disabled: dashboard loads directly, single-user mode.

### State channel

Real-time key/value store for pushing operational state to custom dashboards. State is per-user when auth is enabled, global when disabled.

```bash
# Write state
curl -X POST /api/state/{key} -d '{"data": {"count": 42}}'

# Read state
curl /api/state/{key}

# Subscribe to updates (SSE) — state changes + agent events on one stream
curl -N /api/state/stream              # all keys
curl -N /api/state/stream?keys=a,b     # filter by key
```

SSE events use the event type as the SSE `event:` field (`state.updated`, `message.response`, `job.completed`, etc.), so clients can filter with `addEventListener`.

### Custom dashboard views

Serve project-specific HTML dashboards alongside the built-in React UI. Configured in `crow.yml`:

```yaml
dashboard:
  views:
    trading:
      label: Trading Floor
      path: ./dashboards/trading    # directory with index.html + static assets
```

Views are served at `/dashboard/custom/{name}/` and require auth. The built-in dashboard header shows links to all configured views. Custom dashboards are plain HTML/JS/CSS — no React or build step required. They connect to Crow via the state channel SSE stream and standard API endpoints.

## Custom agents

Define agents as markdown files with YAML frontmatter + prompt body:

```markdown
---
name: my-agent
description: "What this agent does"
tools: [knowledge_search, knowledge_write]
mcp_servers: [web-search]
knowledge_areas: [my-area]
---

You are an agent that...
```

Keep agents in a local folder (e.g. `./agents/`) and sync with `crow agents sync ./agents`. Export with `crow agents export ./agents`.

## Key patterns

- Agents defined in `crow.yml` (built-in) or as markdown files (custom), stored in DB (`agent_defs` table). Prompt template + tools + MCP servers + knowledge areas.
- Knowledge stored as markdown in Postgres with pgvector embeddings (PARA: Projects/Areas/Resources/Archives), scoped per-user when auth enabled.
- Event-driven: components communicate via async event bus, not direct calls.
- iOS app gateway for inbound messages.
- Web dashboard served from FastAPI (React SPA + Vite). Purple theme. Custom HTML dashboards served alongside via `dashboard.views` in `crow.yml`.
- State channel (`state` table): per-user key/value store with SSE streaming. External processes push state via REST, dashboards subscribe via SSE. Agent events (message.*, job.*) piped into the same stream.
- API keys generated from dashboard, bearer token auth for programmatic access.
