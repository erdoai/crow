"""crow init — bootstrap a new project directory."""

import secrets
from pathlib import Path

import typer
from rich.console import Console

console = Console()

CROW_YML_TEMPLATE = """\
# Crow configuration — agent definitions, MCP servers, auth.
# Secrets use ${VAR} syntax, resolved from environment at runtime.

agents: {}
  # my-agent:
  #   description: "What this agent does"
  #   prompt: "You are a helpful agent."
  #   tools: []
  #   mcp: []

mcp: {}
  # web-search:
  #   url: https://search.example.com/mcp
  #   headers:
  #     Authorization: "Bearer ${SEARCH_API_KEY}"

auth:
  enabled: true
  session_secret: ${SESSION_SECRET}
  api_key: ${CROW_API_KEY}
  # passphrase: ${CROW_PASSPHRASE}
  # instance_message: "Welcome! Enter the passphrase to continue."
"""

ENV_TEMPLATE = """\
# Crow environment — set these before running `crow serve`.
# See https://github.com/erdoai/crow for details.

# Database — Postgres connection string (required)
CROW_DATABASE_URL=

# Claude API key (required for agent execution)
CROW_ANTHROPIC_API_KEY=

# Auth secrets (auto-generated)
SESSION_SECRET={session_secret}
CROW_API_KEY={api_key}
CROW_WORKER_API_KEY={worker_key}

# Instance passphrase gate (optional — uncomment to require a shared passphrase before registration)
# CROW_PASSPHRASE=
"""

SAMPLE_AGENT = """\
---
name: hello
description: "A simple greeting agent"
tools: []
---

You are a friendly assistant. Greet the user and help them get started with Crow.
"""


def init_project(
    directory: Path = typer.Argument(
        ".", help="Directory to initialize (defaults to current directory)"
    ),
    with_agents: bool = typer.Option(
        True, "--agents/--no-agents", help="Create sample agents/ directory"
    ),
):
    """Initialize a new Crow project with crow.yml and .env."""
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)

    created = []

    # crow.yml
    crow_yml = directory / "crow.yml"
    if crow_yml.exists():
        console.print("[dim]crow.yml already exists, skipping[/dim]")
    else:
        crow_yml.write_text(CROW_YML_TEMPLATE)
        created.append("crow.yml")

    # .env
    env_file = directory / ".env"
    if env_file.exists():
        console.print("[dim].env already exists, skipping[/dim]")
    else:
        env_file.write_text(
            ENV_TEMPLATE.format(
                session_secret=secrets.token_urlsafe(32),
                api_key=f"crow_{secrets.token_urlsafe(24)}",
                worker_key=secrets.token_urlsafe(24),
            )
        )
        created.append(".env")

    # .gitignore — ensure .env is ignored
    gitignore = directory / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if ".env" not in content:
            with open(gitignore, "a") as f:
                f.write("\n.env\n")
            console.print("[dim]Added .env to .gitignore[/dim]")
    else:
        gitignore.write_text(".env\n")
        created.append(".gitignore")

    # agents/ directory with sample agent
    if with_agents:
        agents_dir = directory / "agents"
        agents_dir.mkdir(exist_ok=True)
        sample = agents_dir / "hello.md"
        if not sample.exists():
            sample.write_text(SAMPLE_AGENT)
            created.append("agents/hello.md")

    if created:
        console.print(f"[green]Initialized crow project in {directory}[/green]")
        for f in created:
            console.print(f"  [dim]created[/dim] {f}")
    else:
        console.print("[dim]Nothing to create — project already initialized[/dim]")

    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print("  1. Edit .env — set CROW_DATABASE_URL and CROW_ANTHROPIC_API_KEY")
    console.print("  2. Edit crow.yml — define your agents and MCP servers")
    console.print("  3. crow serve          # start server")
    console.print("  4. crow worker         # start worker (another terminal)")
    console.print("  5. crow agents sync    # push agents/*.md to server")
