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
scaffold up             # provisions Railway Postgres + server + worker, pushes config
scaffold dev            # runs crow locally, same Railway DB
railway up -d -s <id>   # deploy code changes to Railway
```

## Config

Two-layer config system:
- **`crow.yml`** (gitignored): agent definitions, MCP servers, auth settings. Secrets use `${VAR}` syntax resolved from environment at runtime.
- **Environment variables** with `CROW_` prefix: database URL, API keys, port. See `.env.example`.

In production, `crow.yml` is delivered via the `CROW_CONFIG` env var (set by scaffold from the local file via `${{file:crow.yml}}`). The loader checks `CROW_CONFIG` first, falls back to the file.

### Auth

Auth is optional, configured in the `auth` section of `crow.yml`:
```yaml
auth:
  enabled: true                     # false = single-user, no login
  session_secret: ${SESSION_SECRET}
  api_key: ${CROW_API_KEY}          # static API key (when auth disabled)
  resend:
    api_key: ${RESEND_API_KEY}      # email OTP via Resend
    from: "crow <noreply@erdo.ai>"
```

When enabled: email OTP sign-in → onboarding ("what should I call you?") → dashboard with per-user conversations, knowledge, phone links, API keys. When disabled: dashboard loads directly, single-user mode.

## Key patterns

- Agents defined in `crow.yml` and stored in DB (`agent_defs` table). Prompt template + tools + MCP servers + knowledge areas.
- Knowledge stored as markdown in Postgres with pgvector embeddings (PARA: Projects/Areas/Resources/Archives), scoped per-user when auth enabled.
- Event-driven: components communicate via async event bus, not direct calls.
- iMessage gateway resolves phone numbers to users via `phone_links` table, falls back to allowlist.
- Web dashboard served from FastAPI (Jinja2 templates + vanilla CSS/JS). Purple theme.
- API keys generated from dashboard, bearer token auth for programmatic access.
