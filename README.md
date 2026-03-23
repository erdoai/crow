# crow

The brain for your agentic systems. Crow is an agent coordination platform that monitors, plans, and acts across your autonomous systems — devbot, pilot, trading bots, whatever you run.

Talk to your agents from anywhere: iMessage, a web dashboard, HTTP API, or any MCP-compatible client.

## How it works

```
You (iMessage / API / Dashboard)
  → PA agent (routes your message)
    → Specialist agent (monitor, planner, reviewer, or custom)
      → Tools (MCP servers: devbot, pilot, slack, anything)
        → Response back to you
```

**Server/worker architecture.** The server holds agent definitions, conversations, and a job queue. Workers poll for jobs, run Claude with the agent's tools, and report results. Close your laptop — Railway workers keep going.

**One database everywhere.** Railway Postgres is the single source of truth. Local dev and prod hit the same DB. No sync, no migration drift.

## Quickstart

```bash
# Install
pip install -e .

# Configure
cp crow.yml.example crow.yml    # edit with your agents + MCP servers
cp .env.example .env            # set DATABASE_URL, ANTHROPIC_API_KEY

# Deploy infrastructure (via scaffold)
scaffold up

# Run
crow serve                      # start server
crow worker                     # start worker (separate terminal)

# Talk to it
crow message pa "what's devbot doing?"
```

## Architecture

```
┌──────────────────────────────────────────────┐
│              CROW SERVER                     │
│  FastAPI · Postgres/pgvector · Event bus     │
│  Gateways: iMessage, HTTP API, SSE          │
│  Agent definitions + PARA knowledge in DB    │
└──────────────────┬───────────────────────────┘
                   │
       ┌───────────┴───────────┐
       │                       │
┌──────┴──────┐   ┌────────────┴────┐
│ WORKER      │   │ WORKER          │
│ (local)     │   │ (Railway)       │
│ Runs Claude │   │ Runs Claude     │
│ Calls MCP   │   │ Calls MCP       │
└─────────────┘   └─────────────────┘
```

## Agents

Agents are defined in `crow.yml` — no Python code needed:

```yaml
agents:
  monitor:
    description: "Watches devbot, pilot, trading systems"
    prompt: monitor_system.md.j2
    tools: [knowledge_search, knowledge_write]
    mcp: [devbot, pilot]
    knowledge_areas: [monitoring, incidents]
```

Each agent gets:
- A **system prompt** (Jinja2 template)
- **Built-in tools** — `delegate_to_agent`, `knowledge_search`, `knowledge_write`, `knowledge_archive`
- **MCP tools** — dynamically discovered from connected MCP servers
- **PARA knowledge** — persistent learnings stored in Postgres with optional pgvector semantic search

## MCP integration

External tools are plugged in via [MCP](https://modelcontextprotocol.io/) servers. Crow connects as an HTTP client — no process spawning, no code per integration.

```bash
# Register an MCP server
crow mcp add devbot http://devbot:8484/mcp

# Or in crow.yml
mcp:
  devbot:
    url: http://devbot:8484/mcp
```

Workers discover tools at runtime from each MCP server and pass them to Claude. Any MCP-compatible server works — doesn't matter what language it's written in.

## Configuration

**`crow.yml`** — agents, MCP servers, auth. Auto-imported into DB on first startup.

```bash
crow settings import crow.yml   # reload config into DB
crow settings export            # dump DB config as YAML
```

**Environment variables** — `CROW_` prefix. See [`.env.example`](.env.example).

**`crow.yml` supports `${VAR}` syntax** for env var references:
```yaml
auth:
  session_secret: ${SESSION_SECRET}
```

## CLI

```bash
crow serve                          # start server
crow worker --url http://...        # start worker
crow message <agent> "text"         # send a message
crow status                         # show agents + workers
crow jobs                           # list recent jobs

crow mcp add <name> <url>           # register MCP server
crow mcp list                       # list MCP servers
crow mcp remove <name>              # remove MCP server

crow settings import crow.yml       # import config
crow settings export                # export config
```

## Gateways

- **iMessage** — FSEvents watcher on `chat.db`, sends via AppleScript. Local only.
- **HTTP API** — `POST /messages` for programmatic access. Works everywhere.
- **SSE** — real-time streaming for web/mobile clients.
- **Dashboard** — built-in web UI for conversations and status.

## Knowledge (PARA)

Agents build up persistent knowledge using the [PARA method](https://fortelabs.com/blog/para/):

| Category | Purpose |
|----------|---------|
| **Projects** | Active goals and initiatives |
| **Areas** | Ongoing responsibilities and patterns |
| **Resources** | Reference material |
| **Archives** | Completed or deprecated items |

Knowledge is stored as markdown in Postgres. With pgvector enabled, agents can search semantically. Without it, keyword search still works.

## Deployment

Crow deploys to Railway via [scaffold](docs/scaffold-plan.md):

```yaml
# scaffold.yml
services:
  server:
    provider: railway
    start: "crow serve --port $PORT"
    env:
      CROW_DATABASE_URL: "${{postgres.url}}"
  worker:
    provider: railway
    start: "crow worker --url ${{server.url}}"
databases:
  postgres:
    provider: railway
    plugin: postgres
    extensions: [pgvector]
```

Docker image published to `ghcr.io/erdoai/crow` on every push to main.

## Tech stack

- Python 3.11+, async
- FastAPI + uvicorn
- asyncpg + pgvector
- Anthropic SDK (Claude)
- MCP SDK (tool integration)
- Typer + Rich (CLI)
- watchdog (iMessage gateway)

## License

MIT
