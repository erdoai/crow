# scaffold — Deploy Any Service Stack to Railway/Vercel

## Context

A CLI tool for trivially deploying any service stack — agent systems, web apps, whatever — to Railway/Vercel. The first customer is crow itself (FastAPI server + Postgres/pgvector + worker processes). But it should handle any combination: backend services, frontends, databases, workers, cron jobs.

Agent systems ARE web apps at the infra level: FastAPI + Postgres + background workers. So "deploy a web app" and "deploy an agent system" are the same operation.

Core principle: **one database, local and prod**. The Railway Postgres is the single source of truth. Local dev hits the same DB as prod — no sync, no migration drift, no "works on my machine". This is a personal tool, not a team platform, so shared-DB-by-default is the right call.

## The zero-touch vision

The primary user of scaffold is **Claude Code** (or any coding agent), not a human typing commands. The workflow:

1. You're building an agent system (or anything) with Claude Code
2. You say "deploy this" or the agent decides it needs infra
3. Claude Code reads scaffold's docs, writes a `scaffold.yml`, runs `scaffold up`
4. Infra appears. DB is provisioned. Services are deployed. URLs come back.
5. The agent continues building, now with a live DATABASE_URL and service URLs

**This must be zero-touch.** No interactive prompts, no "go to the Railway dashboard and click...", no manual token setup per project.

### Token resolution

Scaffold resolves provider tokens via a priority chain — env vars take precedence over config file. This means tokens can come from anywhere: a `.env` file another agent wrote, the shell environment, CI, or the global config.

**Resolution order (highest priority first):**

1. **Environment variables** — `SCAFFOLD_RAILWAY_TOKEN`, `SCAFFOLD_VERCEL_TOKEN`, `SCAFFOLD_SUPABASE_TOKEN`, `SCAFFOLD_CLOUDFLARE_API_TOKEN`, `SCAFFOLD_CLOUDFLARE_ACCOUNT_ID`, `SCAFFOLD_CLOUDFLARE_ZONE_ID`, `SCAFFOLD_ANTHROPIC_API_KEY`
2. **Project `.env`** — `.scaffold/.env` in the project directory (scaffold reads this automatically)
3. **Global config** — `~/.scaffold/config.yml`

This means:

- **Human setup**: run `scaffold init`, tokens go in `~/.scaffold/config.yml`, done forever
- **Agent setup**: another agent (e.g. a setup agent with Railway access) writes `.scaffold/.env` with the tokens, then the building agent runs `scaffold up` and it just works
- **CI/CD**: tokens come from environment variables, no config file needed

```bash
# Agent A has Railway auth — writes tokens for Agent B
cat > .scaffold/.env << 'EOF'
SCAFFOLD_RAILWAY_TOKEN=rw_...
SCAFFOLD_CLOUDFLARE_API_TOKEN=cf_...
SCAFFOLD_CLOUDFLARE_ACCOUNT_ID=abc123
SCAFFOLD_CLOUDFLARE_ZONE_ID=def456
EOF

# Agent B (the builder) just runs scaffold — tokens are already there
scaffold up --json
```

### Global config (optional)

`~/.scaffold/config.yml` — for humans who want a one-time setup:

```yaml
tokens:
  railway: "rw_..."
  supabase: "sbp_..."
  vercel: "vercel_..."
  cloudflare:
    api_token: "cf_..."
    account_id: "abc123"
    zone_id: "def456"
  anthropic: "sk-ant-..."

defaults:
  region: us-west1
  domain_suffix: erdo.ai               # auto-generates domains: {project}.erdo.ai, api.{project}.erdo.ai
```

`scaffold init` creates this interactively (the one time you do interact). After that, every `scaffold up` in any project just works. But it's optional — env vars or `.scaffold/.env` work just as well.

### How an agent uses scaffold

Scaffold ships with a `SCAFFOLD.md` reference doc designed to be read by agents. It contains:
- The full `scaffold.yml` schema with every field documented
- Example manifests for common patterns (FastAPI + Postgres, Next.js + API, agent system with workers)
- The exact CLI commands and what they return
- Token resolution — how to pass credentials

An agent building e.g. the agent_trading platform would:

```bash
# 1. Agent reads the scaffold docs
cat $(scaffold docs-path)              # prints path to SCAFFOLD.md

# 2. Agent writes scaffold.yml based on what it's building
cat > scaffold.yml << 'EOF'
project: agent-trading
region: us-west1

services:
  server:
    provider: railway
    runtime: python
    source: .
    start: "python -m agent_trading"
    health_check: /health
    env:
      DATABASE_URL: "${{postgres.url}}"
      REDIS_URL: "${{redis.url}}"
      ANTHROPIC_API_KEY: "${{env.ANTHROPIC_API_KEY}}"

  dashboard:
    provider: railway
    runtime: python
    source: .
    start: "python -m agent_trading.dashboard"
    env:
      DATABASE_URL: "${{postgres.url}}"

databases:
  postgres:
    provider: railway
    plugin: postgres
    extensions: [pgvector]

  redis:
    provider: railway
    plugin: redis

domain:
  server:
    host: api.agent-trading.erdo.ai
    auth: cloudflare-zero-trust
  dashboard:
    host: agent-trading.erdo.ai
    auth: cloudflare-zero-trust
EOF

# 3. Agent provisions everything
scaffold up --json

# 4. scaffold up returns structured output the agent can parse:
# {
#   "status": "ok",
#   "resources": {
#     "postgres": {"url": "postgresql://..."},
#     "redis": {"url": "redis://..."},
#     "server": {"url": "https://agent-trading-server.up.railway.app"},
#     "dashboard": {"url": "https://agent-trading.erdo.ai"}
#   }
# }

# 5. Agent can now use the URLs in subsequent code/config
```

### Machine-readable output

All scaffold commands support `--json` for agent consumption:

```bash
scaffold up --json           # returns structured provisioning result
scaffold status --json       # returns resource status + health
scaffold env pull --json     # returns env vars as JSON object
```

No interactive prompts ever. If something fails, it fails with a structured error the agent can reason about, not a "press Y to continue".

## What it is

A declarative manifest (`scaffold.yml`) + CLI that drives Railway/Vercel CLIs and APIs. Optional LLM-powered `scaffold plan` command generates the manifest from natural language.

## scaffold.yml

```yaml
project: crow
region: us-west1

services:
  server:
    provider: railway
    runtime: python
    source: .
    start: "uvicorn crow.server.app:create_app --factory --host 0.0.0.0 --port $PORT"
    health_check: /health                   # used by scaffold status
    env:
      DATABASE_URL: "${{postgres.url}}"
      CROW_ANTHROPIC_API_KEY: "${{env.ANTHROPIC_API_KEY}}"

  worker:
    provider: railway
    runtime: python
    source: .
    start: "crow worker --url ${{server.url}}"
    replicas: 1                          # scale up as needed
    env:
      CROW_WORKER_API_KEY: "${{env.WORKER_API_KEY}}"

  frontend:                              # optional — not all projects have one
    provider: vercel
    framework: nextjs
    source: ./frontend
    env:
      NEXT_PUBLIC_API_URL: "${{server.url}}"

databases:
  postgres:
    provider: railway
    plugin: postgres
    extensions: [pgvector]               # requested extensions

  redis:                                 # optional
    provider: railway
    plugin: redis

domain:
  server:
    host: api.crow.erdo.ai
    auth: cloudflare-zero-trust          # none | cloudflare-zero-trust | basic
  frontend:
    host: crow.erdo.ai
    auth: none                           # public frontend
```

`${{ref}}` syntax creates implicit dependency graph → topological sort → provision in order.

Key: `services` is a generic list. A "worker" is just another service with a different start command. No special-casing for agent systems vs web apps.

## Commands

```bash
scaffold init              # interactive one-time setup → ~/.scaffold/config.yml
scaffold plan "FastAPI server, 2 workers, Postgres with pgvector on Railway"
# → LLM generates scaffold.yml, opens in editor for review

scaffold up                # provision everything (idempotent)
scaffold up --json         # structured output for agent consumption
scaffold up --dry-run      # show execution plan
scaffold dev               # run services locally, pointing at Railway DB
scaffold status            # provisioned resources + URLs + health checks
scaffold status --json     # machine-readable status
scaffold env sync          # push env vars to providers
scaffold env pull          # pull env vars from providers → local .env
scaffold logs server       # stream logs from a service
scaffold down              # tear down (--keep-db to preserve data)
scaffold down worker       # tear down just one service
scaffold docs-path         # print path to SCAFFOLD.md (for agents to read)
```

### scaffold dev

Runs services locally but uses the provisioned Railway database. No local Postgres needed.

1. Reads `.scaffold/state.json` to get the database connection URL
2. Resolves `${{postgres.url}}` to the real Railway URL, `${{server.url}}` to `localhost:8000`, etc.
3. Runs each service's `start` command as a local process (with [Rich] multiplexed output)
4. Same code, same DB, same env vars (minus provider-specific ones)

This is the whole point: `scaffold up` deploys to Railway, `scaffold dev` runs locally — both hitting the same Postgres. No environment divergence.

### scaffold env pull

Pulls all env vars from Railway/Vercel into a local `.env` file. Useful for onboarding a new machine or after someone updates secrets via the Railway dashboard.

```bash
scaffold env pull              # writes .env
scaffold env pull --stdout     # prints to stdout (for piping)
```

## SCAFFOLD.md — agent-readable reference

Scaffold ships a `SCAFFOLD.md` file that serves as the complete reference for any agent that needs to use it. This is the contract between scaffold and its agent users.

Contents:
- **Schema reference** — every field in `scaffold.yml`, what it does, what's required vs optional, valid values
- **Common patterns** — copy-paste manifests for: FastAPI + Postgres, Next.js + API, Python agent + workers + Redis, full-stack with auth
- **CLI reference** — every command, flags, output format (including `--json` response shapes)
- **Token setup** — how to pass credentials (env vars, `.scaffold/.env`, global config)
- **`${{ref}}` syntax** — how references resolve, what's available (`postgres.url`, `redis.url`, `server.url`, `env.VAR_NAME`)
- **Error reference** — common errors and what they mean

This file is installed alongside the package. `scaffold docs-path` prints its location so agents can `cat` it.

## Documentation

### For developers (humans)

**README.md** — the GitHub landing page:
- What scaffold is (one paragraph + a gif/asciicast of `scaffold up` provisioning a full stack)
- Install: `pipx install scaffold` (or `uv tool install scaffold`)
- Quickstart: `scaffold init` → write `scaffold.yml` → `scaffold up` → done
- Link to full docs

**docs/** — hosted on the repo (or a simple site):
- **Getting started** — install, `scaffold init`, first deploy, `scaffold dev`
- **Manifest reference** — full `scaffold.yml` schema with examples
- **CLI reference** — every command, every flag
- **Providers** — Railway specifics (how projects/services map), Vercel specifics, Cloudflare auth
- **Agent integration** — how to use scaffold from Claude Code, crew, custom agents. The `.scaffold/.env` pattern for token handoff between agents
- **Examples** — complete scaffold.yml files for common stacks:
  - FastAPI + Postgres
  - Next.js + FastAPI + Postgres
  - Python agent system + workers + Redis + pgvector
  - Static site on Vercel

### For agents (SCAFFOLD.md)

Described above — the machine-readable contract. Kept in sync with the human docs but optimised for LLM consumption (flat structure, no navigation, all info in one file).

## Architecture

```
scaffold/
├── pyproject.toml              # hatchling, typer, rich, pydantic, httpx, pyyaml, anthropic
├── CLAUDE.md
├── SCAFFOLD.md                 # agent-readable reference doc (schema, patterns, CLI)
├── README.md
├── docs/
│   ├── getting-started.md
│   ├── manifest-reference.md
│   ├── cli-reference.md
│   ├── providers.md
│   ├── agent-integration.md
│   └── examples.md
├── scaffold/
│   ├── __init__.py
│   ├── __version__.py
│   ├── cli/
│   │   ├── main.py             # Typer: init, plan, up, down, dev, status, env, logs, docs-path
│   │   ├── up.py
│   │   ├── down.py
│   │   ├── dev.py              # local runner with Railway DB
│   │   └── status.py
│   ├── manifest/
│   │   ├── schema.py           # Pydantic models for scaffold.yml
│   │   ├── resolve.py          # ${{ref}} resolution + topological sort
│   │   └── loader.py           # load + validate scaffold.yml
│   ├── providers/
│   │   ├── base.py             # Provider ABC (provision, destroy, get_url, set_env, health_check)
│   │   ├── railway.py          # Railway CLI + GraphQL API wrapper
│   │   └── vercel.py           # Vercel CLI + REST API wrapper
│   ├── planner/
│   │   ├── agent.py            # Claude-based manifest generation
│   │   └── prompts/
│   │       └── plan.md.j2      # system prompt (includes Pydantic schema as context)
│   ├── config/
│   │   ├── tokens.py           # Token resolution: env vars → .scaffold/.env → ~/.scaffold/config.yml
│   │   └── global_config.py    # ~/.scaffold/config.yml loader (defaults)
│   └── state/
│       └── store.py            # .scaffold/state.json — tracks provisioned resources
└── tests/
```

## State tracking

`.scaffold/state.json` after provisioning:
```json
{
  "project": "crow",
  "provisioned_at": "2026-03-22T10:00:00Z",
  "resources": {
    "postgres": {
      "provider": "railway",
      "railway_project_id": "abc123",
      "railway_service_id": "def456",
      "url": "postgresql://...",
      "url_var": "DATABASE_URL"
    },
    "redis": {
      "provider": "railway",
      "railway_project_id": "abc123",
      "railway_service_id": "uvw890",
      "url": "redis://..."
    },
    "server": {
      "provider": "railway",
      "railway_service_id": "ghi789",
      "url": "https://crow-server.up.railway.app"
    },
    "worker": {
      "provider": "railway",
      "railway_service_id": "jkl012"
    },
    "frontend": {
      "provider": "vercel",
      "vercel_project_id": "mno345",
      "url": "https://crow.vercel.app"
    }
  }
}
```

Makes `up` idempotent (update not recreate), `down` possible (knows what to destroy), and `dev` possible (knows the DB URL without re-querying Railway).

## Dependencies

```
typer, rich, pydantic, pyyaml, httpx, anthropic
```

External prerequisites: `railway` CLI, `vercel` CLI (or `npx vercel`).

## Implementation order

1. pyproject.toml, structure, CLAUDE.md, SCAFFOLD.md, README.md
2. Token resolution (`config/tokens.py` — env vars → `.scaffold/.env` → `~/.scaffold/config.yml`)
3. Global config loader (`~/.scaffold/config.yml` — defaults, domain_suffix)
4. Manifest schema (Pydantic) + loader + `${{ref}}` resolver (topo sort)
5. State store (`.scaffold/state.json`)
6. Railway provider (provision Postgres/Redis + extensions, deploy service, get URL, set env, health check)
7. `scaffold up` + `--json` output (orchestrate providers in dependency order, idempotent)
8. `scaffold dev` (local runner pointing at Railway DB)
9. `scaffold status` + `scaffold down`
10. `scaffold env sync` + `scaffold env pull`
11. Vercel provider (create project, deploy, get URL, set env)
12. `scaffold plan` (Claude generates manifest from natural language)
13. `scaffold logs` (stream from Railway/Vercel)
14. Domain + auth config (Cloudflare Zero Trust + DNS integration)
15. `scaffold init` (interactive one-time setup of `~/.scaffold/config.yml`)
16. Docs (getting-started, manifest-reference, CLI reference, examples)

## Integration with agents

Any agent (Claude Code, crow, custom) can use scaffold by:

1. Reading `SCAFFOLD.md` (via `scaffold docs-path`) to understand the schema
2. Writing a `scaffold.yml` for whatever it's building
3. Running `scaffold up --json` to provision and get back URLs
4. Using those URLs in the code it's writing

The agent never touches tokens, dashboards, or provider UIs. It just describes what it needs and scaffold makes it exist.

### Multi-agent token handoff

For setups where one agent manages auth and another builds:

```
Agent A (infra/auth agent)              Agent B (builder agent)
├── has Railway/Cloudflare tokens       ├── has no provider tokens
├── writes .scaffold/.env               ├── reads SCAFFOLD.md
│   with SCAFFOLD_RAILWAY_TOKEN etc.    ├── writes scaffold.yml
└── done                                ├── runs scaffold up --json
                                        │   (tokens resolved from .scaffold/.env)
                                        └── uses returned URLs in code
```

This separation means the builder agent never needs provider credentials in its own context — it just needs scaffold installed and a `.scaffold/.env` present.
