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
pip install -e .

# Configure
cp crow.yml.example crow.yml    # define your agents + MCP servers
cp .env.example .env            # set DATABASE_URL, ANTHROPIC_API_KEY

# Run
crow serve                      # start server
crow worker                     # start worker (separate terminal)

# Talk to it
crow message pa "hello"
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
- **Built-in tools** — `delegate_to_agent`, `knowledge_search`, `knowledge_write`, `knowledge_archive`
- **MCP tools** — dynamically discovered from connected MCP servers
- **PARA knowledge** — persistent learnings in Postgres (Projects, Areas, Resources, Archives)

## MCP integration

Connect any MCP server to give agents new capabilities:

```bash
crow mcp add my-tools http://localhost:3001/mcp
```

Or in `crow.yml`:

```yaml
mcp:
  my-tools:
    url: http://localhost:3001/mcp
```

Workers discover tools from each MCP server at job start and pass them to Claude alongside the built-in tools.

## Configuration

**`crow.yml`** — agents, MCP servers, auth. Auto-imported into DB on first startup.

```bash
crow settings import crow.yml   # reload config into DB
crow settings export            # dump current config as YAML
```

**Environment variables** — `CROW_` prefix. See [`.env.example`](.env.example).

`crow.yml` supports **`${VAR}` syntax** for env var references.

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

Deploy with [scaffold](docs/scaffold-plan.md) or any Docker-compatible platform:

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
```

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

## Tech stack

- Python 3.11+, async
- FastAPI + uvicorn
- asyncpg + pgvector
- Anthropic SDK (Claude)
- MCP SDK (tool integration)
- Typer + Rich (CLI)

## License

[FCL-1.0-ALv2](LICENSE) (Fair Core License — converts to Apache 2.0 after 2 years)
