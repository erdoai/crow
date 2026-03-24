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

# Custom dashboards
crow dashboard upload NAME ./path  # upload a dashboard directory to the server
crow dashboard list                # list all dashboard views
crow dashboard delete NAME         # delete a DB-stored dashboard view
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
parent: null                    # omit for top-level (user-facing) agents
tools: [knowledge_search, knowledge_write]
mcp_servers: [my-tools]        # list of names, or dict of inline configs (see below)
knowledge_areas: [my-area]
max_iterations: 25
---

Your system prompt here. This is sent as the system message when the agent runs.
You can use multiple paragraphs, lists, code blocks — any markdown.
```

**Inline MCP servers** — instead of referencing instance-level names, define configs directly in frontmatter. Inline configs override instance-level servers of the same name:

```yaml
mcp_servers:
  my-tools:
    url: https://my-mcp.example.com/mcp
    headers:
      Authorization: "Bearer ${MY_KEY}"
```

**Frontmatter fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Unique identifier (kebab-case) |
| `description` | yes | Short description shown in dashboard and used by PA for routing |
| `parent` | no | Name of parent agent. Sub-agents are hidden from the UI and only invoked via delegation. Omit for top-level (user-facing) agents |
| `tools` | no | List of built-in tools to enable |
| `mcp_servers` | no | List of MCP server names (instance-level refs) **or** dict of inline MCP configs. Inline configs override instance-level servers of the same name |
| `knowledge_areas` | no | Scopes for PARA knowledge reads/writes |
| `max_iterations` | no | Max tool-use loops for this agent (defaults to server default) |

**Available built-in tools:** `delegate_to_agent`, `delegate_parallel`, `knowledge_search`, `knowledge_write`, `knowledge_archive`, `create_agent`, `list_agents`, `delete_agent`, `schedule`, `progress_update`, `create_attachment`, `execute_code`

### Sub-agents and orchestration

Agents with a `parent` field are **sub-agents** — hidden from the UI and only invoked via delegation from their parent. Agents without `parent` are top-level (user-facing).

**`delegate_parallel`** is a built-in tool for running multiple sub-agents concurrently. Use it alongside `delegate_to_agent` (sequential) in orchestrator agents.

Parent agents automatically receive a `{{ sub_agents }}` Jinja2 variable in their prompt context, listing their children's names and descriptions. Use it to tell the orchestrator what's available:

```markdown
---
name: trading
tools: [delegate_to_agent, delegate_parallel]
max_iterations: 25
---

You orchestrate analysis across these specialists:
{% for agent in sub_agents %}
- {{ agent.name }}: {{ agent.description }}
{% endfor %}
```

**API behavior:** `GET /api/agents` returns top-level agents by default. Use `?parent=<name>` to list a specific agent's sub-agents, or `?all=true` to list everything.

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

# Custom dashboard views — file-based (same repo) or uploaded via API
dashboard:
  views:
    trading:
      label: Trading Floor
      path: ./dashboards/trading      # file-based: directory with index.html + assets

# Auth (enabled by default)
auth:
  enabled: true
  session_secret: ${SESSION_SECRET}
  api_key: ${CROW_API_KEY}
  passphrase: ${CROW_PASSPHRASE}                    # optional — gate registration behind a shared passphrase
  instance_message: "Welcome! Enter the passphrase." # optional — shown before passphrase prompt
  resend:
    api_key: ${RESEND_API_KEY}
    from: ${RESEND_FROM}
```

Secrets use `${VAR}` syntax, resolved from environment at runtime. In production, the entire file can be delivered via the `CROW_CONFIG` env var.

### Scheduling and progress

**`schedule`** — lets an agent schedule a future job (one-shot or recurring). Use for heartbeats (agent schedules itself), delayed follow-ups, or periodic tasks. Set `replace: true` to cancel existing active schedules for the same agent+conversation before creating a new one — this prevents duplicate heartbeats.

```markdown
tools: [schedule, progress_update]
```

The agent provides `agent_name` + `input` + either `delay_seconds` (one-shot) or `cron` (recurring, e.g. `*/5 * * * *`). Scheduled jobs are stored in the `scheduled_jobs` table and promoted to pending jobs by a server-side scheduler loop (10s poll interval).

**`progress_update`** — publishes a real-time status update during an agent run. Writes to the state channel under key `progress:{job_id}`, so dashboards can subscribe via SSE (`/api/state/stream?keys=progress:*`).

### File attachments

Messages support file attachments. Users upload files via multipart `POST /messages`, and agents create attachments via the `create_attachment` built-in tool.

**User uploads:** Send a multipart/form-data request with `text`, `thread_id`, and `files` fields. Files are stored as base64 in the `attachments` table and passed to Claude as native content blocks (images as `image` blocks, PDFs as `document` blocks).

**Agent attachments:** The `create_attachment` tool takes `filename`, `content` (text), and optional `content_type` (default `text/plain`). The attachment is linked to the agent's response message and downloadable via `GET /attachments/{id}/download`.

**Conversation messages API** (`GET /conversations/{id}/messages`) returns attachment metadata (id, filename, content_type, size_bytes) on each message — data is omitted (clients download separately).

**Attachments API:**
```
GET  /attachments/{id}/download        # download attachment file
POST /jobs/{job_id}/attachments        # worker-facing: create attachment during execution
```

**Scheduled jobs API:**
```
GET    /scheduled-jobs          # list scheduled jobs (user-scoped)
DELETE /scheduled-jobs/{id}     # cancel a scheduled job
```

### Code execution (E2B)

**`execute_code`** — runs Python code in a sandboxed [E2B](https://e2b.dev) environment. Sandboxes are created on demand (120s timeout), execute the code, and are torn down. No MCP server needed.

Parameters: `code` (required), `packages` (optional list of pip packages to install before running).

Returns stdout, stderr, errors, and cell results. Requires `E2B_API_KEY` environment variable on the worker.

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
POST /api/messages                     # trigger an agent (JSON or multipart with files)
GET  /api/agents                       # list top-level agents (add ?parent=X or ?all=true)
GET  /api/jobs                         # list jobs
GET  /api/conversations/{id}/messages  # conversation history
```

All endpoints are **same-origin** when the dashboard is served by Crow (at `/dashboard/custom/{name}/`), so no CORS config is needed — just use relative paths (`/api/state/stream`) in your JS. Auth is handled by the session cookie automatically.

All endpoints require auth (session cookie or `Authorization: Bearer <api-key>` header). Conversations, messages, jobs, and state are scoped to the authenticated user.

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

Auth is **enabled by default**. All API endpoints are user-scoped — conversations, messages, jobs, knowledge, and state are isolated per-user. Configured in the `auth` section of `crow.yml`:
```yaml
auth:
  enabled: true                     # false = single-user, no login (not recommended)
  session_secret: ${SESSION_SECRET}
  api_key: ${CROW_API_KEY}          # static API key fallback
  passphrase: ${CROW_PASSPHRASE}    # optional — require shared passphrase before registration
  instance_message: "Welcome!"      # optional — shown before passphrase prompt
  resend:
    api_key: ${RESEND_API_KEY}      # email OTP via Resend
    from: ${RESEND_FROM}             # defaults to "crow <noreply@erdo.ai>"
```

When enabled: email OTP sign-in → onboarding ("what should I call you?") → dashboard with per-user conversations, knowledge, phone links, API keys. When disabled: dashboard loads directly, single-user mode (all data shared).

**Instance passphrase gate:** Set `passphrase` in the auth config (via `CROW_PASSPHRASE` env var) to require a shared passphrase before users can register. Useful for web-exposed instances. Optionally set `instance_message` to show a welcome message before the passphrase prompt. When configured, the login flow becomes: instance message → passphrase → email OTP → onboarding. The passphrase is validated server-side and a 24-hour gate cookie is issued so returning users don't re-enter it. API key and worker auth are unaffected.

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

### Scoping model (dashboards and agents)

Dashboards and agents have three visibility levels:

| Level | `user_id` | How created | Visibility |
|-------|-----------|-------------|------------|
| **Instance-level** | NULL | Uploaded with the static API key (`CROW_API_KEY` from crow.yml), or configured in `crow.yml` | All users |
| **User-level (private)** | set | Uploaded with a personal API key (generated from dashboard) | Only that user |
| **Shared** | set | User-level, but accessed via share link (`?token=xxx`) | Anyone with the link |

**How it works in practice:**
- The static API key (`CROW_API_KEY` from crow.yml) maps to no user — uploads are instance-level (global).
- A personal API key (generated from the dashboard settings page) maps to your user — uploads are scoped to you.
- List endpoints (`GET /api/dashboard/views`, `GET /api/agents`) return your own items + instance-level items.
- Other users never see your private dashboards or agents.

**CLI usage with personal API key:**
```bash
# Instance-level (visible to all users)
export CROW_API_KEY=crow_static_key_from_config
crow dashboard upload shared-dash ./dashboard

# User-level (private to you)
export CROW_API_KEY=crow_your_personal_api_key
crow dashboard upload my-dash ./dashboard
```

**Share links:** Dashboards can be shared via a token-based URL (`/dashboard/custom/{name}/?token=xxx`). The share token is generated when a user shares a dashboard. Anyone with the link can view the dashboard without logging in.

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

**Uploading dashboards via API/CLI (no files on server disk):**

External projects can upload dashboard files to a running Crow instance without needing files on the server filesystem. Files are stored as base64-encoded JSONB in the `dashboard_views` table.

```bash
# Upload a dashboard directory
crow dashboard upload trading ./dashboards/trading --label "Trading Floor"

# Or via API (JSON)
curl -X POST /api/dashboard/views \
  -H 'Content-Type: application/json' \
  -d '{"name": "trading", "label": "Trading Floor", "files": {"index.html": "<base64>", "app.js": "<base64>"}}'

# List all views (file-based + DB-stored)
crow dashboard list

# Delete a DB-stored view
crow dashboard delete trading
```

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
