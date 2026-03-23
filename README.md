# crow

An open-source agent coordination platform. Define AI agents in YAML, connect them to any tools via MCP, and interact through a web dashboard, HTTP API, or mobile app.

## How it works

```
You (Dashboard / API / Mobile)
  → PA agent (routes your message to the right specialist)
    → Agent (runs with its own prompt, tools, and knowledge)
      → Tools (built-in + any MCP server)
        → Response back to you
```

**Server/worker architecture.** The server manages agent definitions, conversations, knowledge, and a job queue. Workers poll for jobs, run Claude with the agent's configured tools, and report results. Workers can run anywhere — local machine, cloud, Railway.

**Agents are YAML, not code.** Define agents in `crow.yml` with a prompt template, tools, and knowledge areas. No Python needed per agent.

**Tools via MCP.** External tools are plugged in via [MCP](https://modelcontextprotocol.io/) servers. Crow connects as an HTTP client and discovers tools at runtime. Any MCP-compatible server works, regardless of language.

## Quickstart

```bash
# Install
pip install crow-agents

# Initialize a new project
crow init
# edit .env — set CROW_DATABASE_URL and CROW_ANTHROPIC_API_KEY

# Run
crow serve                      # start server
crow worker                     # start worker (separate terminal)

# Sync your agents and talk to them
crow agents sync ./agents
crow message hello "hi there"
```

Or install from source:

```bash
pip install git+https://github.com/erdoai/crow.git
```

## Architecture

```
┌──────────────────────────────────────────────┐
│              CROW SERVER                     │
│  FastAPI · Postgres/pgvector · Event bus     │
│  Gateways: HTTP API, SSE, Web dashboard     │
│  Agent definitions + PARA knowledge in DB    │
└──────────────────┬───────────────────────────┘
                   │
       ┌───────────┴───────────┐
       │                       │
┌──────┴──────┐   ┌────────────┴────┐
│ WORKER      │   │ WORKER          │
│ (local)     │   │ (cloud)         │
│ Runs Claude │   │ Runs Claude     │
│ Calls MCP   │   │ Calls MCP       │
└─────────────┘   └─────────────────┘
```

## Agents

Define agents in `crow.yml`:

```yaml
agents:
  assistant:
    description: "General purpose assistant"
    prompt: assistant.md.j2
    tools: [knowledge_search, knowledge_write]
    mcp: [my-tools]
    knowledge_areas: [general]
```

Each agent gets:
- A **system prompt** (Jinja2 template in `crow/agents/prompts/`)
- **Built-in tools** — `delegate_to_agent`, `knowledge_search`, `knowledge_write`, `knowledge_archive`, `create_agent`, `list_agents`, `delete_agent`
- **MCP tools** — dynamically discovered from connected MCP servers
- **PARA knowledge** — persistent learnings in Postgres (Projects, Areas, Resources, Archives)

## Custom agents

Define agents as markdown files and sync them to any crow instance:

```markdown
---
name: researcher
description: "Researches topics and saves findings"
tools: [knowledge_search, knowledge_write]
mcp_servers: [web-search]
knowledge_areas: [research]
---

You are a research agent. When given a topic, search the web for relevant
information, synthesize it, and save key findings to your knowledge base.
```

Keep agents in a local folder and sync:

```bash
crow agents sync ./agents       # push local .md files to the server
crow agents export ./agents     # pull all agents as .md files
```

## MCP integration

Connect any MCP server to give agents new capabilities:

```bash
crow mcp add my-tools http://localhost:3001/mcp
```

Or in `crow.yml` (with optional auth headers):

```yaml
mcp:
  web-search:
    url: https://mcp.example.com/v1
    headers:
      Authorization: "Bearer ${MY_API_KEY}"
```

Any MCP server with an HTTP endpoint works. Workers discover tools from each server at job start and pass them to Claude alongside the built-in tools.

## Configuration

| File | Purpose |
|------|---------|
| `crow.yml` | Agent definitions, MCP servers, auth settings |
| `scaffold.config.yml` | Required/optional API keys + auto-generated secrets |
| `scaffold.yml` | Infrastructure manifest (Railway services, databases, domains) |
| `.env.example` | Reference for all environment variables |

**`crow.yml`** — agents, MCP servers, auth. Auto-imported into DB on first startup. Supports `${VAR}` syntax for env var references.

```bash
crow settings import crow.yml   # reload config into DB
crow settings export            # dump current config as YAML
```

**`scaffold.config.yml`** — declares what API keys the project needs. On `scaffold up`, it auto-generates secrets and prompts for missing required keys. Everything is stored in `.scaffold/.env` (gitignored).

## CLI

```bash
crow init                              # initialize new project
crow serve                          # start server
crow worker --url http://...        # start worker
crow message <agent> "text"         # send a message
crow status                         # show agents + workers
crow jobs                           # list recent jobs

crow agents sync <folder>              # sync .md agent files to server
crow agents export <folder>            # export agents as .md files

crow mcp add <name> <url>              # register MCP server
crow mcp list                          # list MCP servers
crow mcp remove <name>                 # remove MCP server

crow settings import crow.yml       # import config
crow settings export                # export config

crow dashboard upload <name> <dir>    # upload custom dashboard files
crow dashboard list                   # list all dashboard views
crow dashboard delete <name>          # delete a dashboard view
```

## Using Crow from another project

You don't need to clone this repo. Install, init, and point at your server:

```bash
pip install crow-agents
crow init                                # creates crow.yml, .env, agents/
# Edit .env — set CROW_DATABASE_URL and CROW_ANTHROPIC_API_KEY
# Create agents as .md files with YAML frontmatter:
```

```markdown
---
name: my-agent
description: "What this agent does"
tools: [knowledge_search, knowledge_write]
mcp_servers: [my-tools]
knowledge_areas: [my-area]
---

Your system prompt here...
```

```bash
crow serve                               # start server
crow worker                              # start worker
crow agents sync ./agents                # push agents to server
crow mcp add my-tools https://my-mcp/mcp # register external tools
crow dashboard upload trading ./dashboard --label "Trading Floor"
```

Custom dashboards are plain HTML/JS/CSS — no React or build step needed. They're served at `/dashboard/custom/{name}/` and connect to Crow APIs via same-origin requests (SSE for real-time state, REST for triggers).

**API for custom dashboards and integrations:**

| Endpoint | Description |
|----------|-------------|
| `GET /api/state/stream` | SSE stream — real-time state changes + agent events |
| `POST/GET /api/state/{key}` | Read/write key/value state |
| `POST /api/messages` | Trigger an agent |
| `GET /api/agents` | List agents |
| `GET /api/jobs` | List jobs |

See [CLAUDE.md](CLAUDE.md) for the full integration guide: agent markdown format, crow.yml reference, dashboard contract, and MCP server pattern.

## Gateways

- **HTTP API** — `POST /messages` for programmatic access
- **SSE** — real-time streaming for web and mobile clients
- **Web dashboard** — built-in UI for conversations and status

## Knowledge (PARA)

Agents build persistent knowledge using the [PARA method](https://fortelabs.com/blog/para/):

| Category | Purpose |
|----------|---------|
| **Projects** | Active goals and initiatives |
| **Areas** | Ongoing responsibilities and patterns |
| **Resources** | Reference material |
| **Archives** | Completed or deprecated items |

Stored as markdown in Postgres. With pgvector enabled, agents can search semantically. Without it, keyword search works.

## Deployment

Docker image published to `ghcr.io/erdoai/crow` on every push to main.

Deploy with [scaffold](https://github.com/erdoai/scaffold) or any Docker-compatible platform:

```yaml
# scaffold.yml
services:
  server:
    provider: railway
    start: "crow serve"
    env:
      CROW_DATABASE_URL: "${{postgres.url}}"
  worker:
    provider: railway
    start: "crow worker"
    env:
      CROW_SERVER_URL: "${{server.url}}"
databases:
  postgres:
    provider: railway
    plugin: postgres
```

`crow serve` reads `$PORT` automatically (Railway sets it). `crow worker` reads `$CROW_SERVER_URL` to find the server — no hardcoded URLs.

## Auth (optional)

Email-based authentication with magic codes via Resend. API key auth for programmatic access. Disabled by default.

```yaml
# crow.yml
auth:
  enabled: true
  session_secret: ${SESSION_SECRET}
  resend:
    api_key: ${RESEND_API_KEY}
```

### Dashboard and agent scoping

Dashboards and agents support three visibility levels:

- **Instance-level** — uploaded with the static `CROW_API_KEY` from `crow.yml`, or configured directly in `crow.yml`. Visible to all users.
- **User-level (private)** — uploaded with a personal API key (generated from the dashboard settings page). Only visible to that user.
- **Shared** — a user-level dashboard made accessible to anyone via a share link (`?token=xxx`).

List endpoints return your own items plus all instance-level items. Other users never see your private dashboards or agents.

```bash
# Instance-level (visible to all users)
export CROW_API_KEY=crow_static_key_from_config
crow dashboard upload shared-dash ./dashboard

# User-level (private to you)
export CROW_API_KEY=crow_your_personal_api_key
crow dashboard upload my-dash ./dashboard
```

## Tech stack

- Python 3.11+, async
- FastAPI + uvicorn
- asyncpg + pgvector
- Anthropic SDK (Claude)
- MCP SDK (tool integration)
- Typer + Rich (CLI)

## License

[FCL-1.0-ALv2](LICENSE) (Fair Core License — converts to Apache 2.0 after 2 years)
