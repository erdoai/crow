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

### Typical workflow from an external project

```bash
pip install crow-agents
crow init                          # creates crow.yml, .env, agents/
# Edit .env — set CROW_DATABASE_URL and CROW_ANTHROPIC_API_KEY
# Edit crow.yml — define agents, MCP servers, dashboard views
# Create agent .md files in agents/

# If running your own server:
crow serve
crow worker

# If pointing at a remote server (e.g. Railway):
crow agents sync ./agents --url https://your-crow-server.railway.app
crow mcp add my-tools https://my-mcp-server.railway.app/mcp --url https://your-crow-server.railway.app
```

### Agent markdown format

Agents are markdown files with YAML frontmatter. The frontmatter defines metadata and capabilities; the body is the system prompt.

```markdown
---
name: agent-name
description: "What this agent does"
tools: [knowledge_search, knowledge_write]
mcp_servers: [my-tools]
knowledge_areas: [my-area]
---

Your system prompt here. This is sent as the system message when the agent runs.
You can use multiple paragraphs, lists, code blocks — any markdown.
```

**Frontmatter fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Unique identifier (kebab-case) |
| `description` | yes | Short description shown in dashboard and used by PA for routing |
| `tools` | no | List of built-in tools to enable |
| `mcp_servers` | no | List of MCP server names (must match names in `crow.yml` or registered via CLI) |
| `knowledge_areas` | no | Scopes for PARA knowledge reads/writes |

**Available built-in tools:** `delegate_to_agent`, `knowledge_search`, `knowledge_write`, `knowledge_archive`, `create_agent`, `list_agents`, `delete_agent`

### crow.yml reference

```yaml
# Agent definitions (alternative to .md files — these are loaded into DB on startup)
agents:
  assistant:
    description: "General purpose assistant"
    prompt: assistant.md.j2           # Jinja2 template in crow/agents/prompts/
    tools: [knowledge_search]
    mcp: [web-search]
    knowledge_areas: [general]

# MCP server connections — tools discovered at runtime via HTTP
mcp:
  web-search:
    url: https://mcp.example.com/v1
    headers:
      Authorization: "Bearer ${MY_API_KEY}"

# Custom dashboard views served alongside the built-in UI
dashboard:
  views:
    trading:
      label: Trading Floor
      path: ./dashboards/trading      # directory with index.html + static assets

# Auth (optional — disabled by default)
auth:
  enabled: true
  session_secret: ${SESSION_SECRET}
  api_key: ${CROW_API_KEY}
  resend:
    api_key: ${RESEND_API_KEY}
    from: ${RESEND_FROM}
```

Secrets use `${VAR}` syntax, resolved from environment at runtime. In production, the entire file can be delivered via the `CROW_CONFIG` env var.

### Custom dashboard API contract

Custom dashboards are plain HTML/JS/CSS served from a directory. They connect to Crow via these endpoints:

**SSE (real-time updates):**
```
GET /api/state/stream                  # all state changes + agent events
GET /api/state/stream?keys=a,b        # filter by key
```
Events use the SSE `event:` field (`state.updated`, `message.response`, `job.completed`, etc.) so clients can use `addEventListener` to filter.

**State (key/value store):**
```
POST /api/state/{key}                  # write: {"data": {...}}
GET  /api/state/{key}                  # read current value
```

**Agents and messages:**
```
POST /api/messages                     # trigger an agent: {"agent": "name", "content": "..."}
GET  /api/agents                       # list agents
GET  /api/jobs                         # list jobs
GET  /api/conversations/{id}/messages  # conversation history
```

All endpoints require auth (session cookie or `Authorization: Bearer <api-key>` header) when auth is enabled.

### MCP server pattern

External projects host their own MCP servers. Crow connects as an HTTP client and discovers tools at runtime — no tool registration or schema needed in crow.yml.

```bash
# Register an MCP server
crow mcp add my-tools https://my-mcp-server.example.com/mcp

# With auth (if the MCP server requires a bearer token)
# Add to crow.yml:
#   mcp:
#     my-tools:
#       url: https://my-mcp-server.example.com/mcp
#       headers:
#         Authorization: "Bearer ${MY_TOOLS_API_KEY}"
```

MCP servers can be written in any language. Workers call `tools/list` on each server at job start to discover available tools, then pass them to Claude alongside built-in tools. The MCP server is responsible for its own auth — Crow forwards the configured headers on every request.

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
