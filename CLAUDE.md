# crow

Agent coordination and monitoring system. The "brain" that orchestrates devbot, pilot, erdo, and other agentic systems.

## Architecture

Server/worker model:
- **Server** (FastAPI): holds agent definitions, knowledge (PARA in pgvector), conversations, job queue. Gateways (iMessage, HTTP API) feed inbound messages.
- **Workers**: poll server for jobs, execute agent runs (Claude API calls), report results.
- **PA agent**: top-level agent that routes all inbound messages to specialist agents.

**One database, local and prod.** Railway Postgres (provisioned via scaffold) is the single source of truth. Local dev and prod hit the same DB — no docker-compose, no local Postgres, no migration drift.

## Tech stack

- Python 3.11+, async-first
- FastAPI + uvicorn (server)
- asyncpg + pgvector (database — Railway Postgres)
- Anthropic SDK (Claude API)
- Typer (CLI), Rich (output)
- Pydantic + pydantic-settings (config/models)
- Jinja2 (prompt templates)
- watchdog (iMessage FSEvents gateway)

## Commands

```bash
crow serve              # start server
crow worker             # start worker (polls server for jobs)
crow message <agent> "text"  # send a test message
crow status             # system status
crow jobs               # list jobs
```

## Development

```bash
pip install -e ".[dev]" # install with dev deps
# Set CROW_DATABASE_URL to your Railway Postgres URL (from scaffold)
crow serve              # start server on :8100
crow worker             # start worker in another terminal
ruff check .            # lint
pytest                  # test
```

## Deployment

Infrastructure provisioned via [scaffold](docs/scaffold-plan.md):
```bash
scaffold up             # provisions Railway Postgres + server + worker
scaffold dev            # runs crow locally, same Railway DB
```

## Config

All config via environment variables with `CROW_` prefix. See `.env.example`.

## Key patterns

- Agents are defined as: prompt template + tools + knowledge areas (see `crow/agents/definitions/`)
- Knowledge stored as markdown in Postgres with pgvector embeddings (PARA: Projects/Areas/Resources/Archives)
- Event-driven: components communicate via async event bus, not direct calls
- Knowledge injected into agent context as tool_use/tool_result pairs
