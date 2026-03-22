"""CLI entry point — Typer app."""

import asyncio
import logging

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from crow.config.settings import Settings

app = typer.Typer(
    name="crow", help="Agent coordination and monitoring system."
)
mcp_app = typer.Typer(help="Manage MCP servers.")
settings_app = typer.Typer(help="Import/export config.")
app.add_typer(mcp_app, name="mcp")
app.add_typer(settings_app, name="settings")

console = Console()
LOG_FMT = "%(asctime)s %(name)s %(levelname)s %(message)s"
DEFAULT_URL = "http://localhost:8100"


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8100, help="Port to bind to"),
):
    """Start the crow server."""
    logging.basicConfig(level=logging.INFO, format=LOG_FMT)
    uvicorn.run(
        "crow.server.app:create_app",
        host=host,
        port=port,
        factory=True,
    )


@app.command()
def worker(
    server_url: str = typer.Option(
        DEFAULT_URL, "--url", help="Crow server URL"
    ),
):
    """Start a crow worker that polls the server for jobs."""
    logging.basicConfig(level=logging.INFO, format=LOG_FMT)
    from crow.worker.loop import worker_loop

    settings = Settings()
    asyncio.run(worker_loop(server_url, settings))


@app.command()
def message(
    agent: str = typer.Argument(help="Agent name"),
    text: str = typer.Argument(help="Message text"),
    server_url: str = typer.Option(
        DEFAULT_URL, "--url", help="Crow server URL"
    ),
):
    """Send a message to an agent (via API gateway)."""
    import httpx

    resp = httpx.post(
        f"{server_url}/messages",
        json={"text": text, "thread_id": f"cli-{agent}"},
    )
    resp.raise_for_status()
    console.print(f"[green]Message sent[/green]: {text}")


@app.command()
def status(
    server_url: str = typer.Option(
        DEFAULT_URL, "--url", help="Crow server URL"
    ),
):
    """Show system status."""
    import httpx

    try:
        agents_data = httpx.get(f"{server_url}/agents").json()
        table = Table(title="Agents")
        table.add_column("Name")
        table.add_column("Description")
        for a in agents_data:
            table.add_row(a["name"], a["description"])
        console.print(table)

        workers_data = httpx.get(f"{server_url}/workers").json()
        if workers_data:
            wtable = Table(title="Workers")
            wtable.add_column("ID")
            wtable.add_column("Name")
            wtable.add_column("Status")
            wtable.add_column("Last Heartbeat")
            for w in workers_data:
                wtable.add_row(
                    w["id"],
                    w.get("name", ""),
                    w["status"],
                    str(w["last_heartbeat"]),
                )
            console.print(wtable)
        else:
            console.print("[yellow]No workers connected[/yellow]")

    except httpx.HTTPError as e:
        console.print(f"[red]Cannot reach server: {e}[/red]")


@app.command(name="jobs")
def list_jobs(
    status_filter: str | None = typer.Option(
        None, "--status", help="Filter by status"
    ),
    limit: int = typer.Option(20, "--limit", help="Max jobs to show"),
    server_url: str = typer.Option(
        DEFAULT_URL, "--url", help="Crow server URL"
    ),
):
    """List recent jobs."""
    import httpx

    try:
        params: dict = {"limit": limit}
        if status_filter:
            params["status"] = status_filter
        jobs_data = httpx.get(
            f"{server_url}/jobs", params=params
        ).json()

        if not jobs_data:
            console.print("[dim]No jobs[/dim]")
            return

        table = Table(title="Jobs")
        table.add_column("ID", max_width=12)
        table.add_column("Agent")
        table.add_column("Status")
        table.add_column("Input", max_width=40)
        table.add_column("Created")
        for j in jobs_data:
            table.add_row(
                j["id"][:12],
                j["agent_name"],
                j["status"],
                (j["input"] or "")[:40],
                str(j.get("created_at", "")),
            )
        console.print(table)

    except httpx.HTTPError as e:
        console.print(f"[red]Cannot reach server: {e}[/red]")


# -- MCP subcommands --


@mcp_app.command("add")
def mcp_add(
    name: str = typer.Argument(help="MCP server name"),
    command: str | None = typer.Option(
        None, "--command", help="Command for stdio transport"
    ),
    url: str | None = typer.Option(
        None, "--url", help="URL for http transport"
    ),
    transport: str = typer.Option(
        "stdio", "--transport", help="Transport type"
    ),
    server_url: str = typer.Option(
        DEFAULT_URL, "--server", help="Crow server URL"
    ),
):
    """Add an MCP server."""
    import httpx

    if not command and not url:
        console.print("[red]Must provide --command or --url[/red]")
        raise typer.Exit(1)
    if url and transport == "stdio":
        transport = "http"

    resp = httpx.post(
        f"{server_url}/mcp-servers",
        json={
            "name": name,
            "transport": transport,
            "command": command,
            "url": url,
        },
    )
    resp.raise_for_status()
    console.print(f"[green]Added MCP server:[/green] {name}")


@mcp_app.command("list")
def mcp_list(
    server_url: str = typer.Option(
        DEFAULT_URL, "--server", help="Crow server URL"
    ),
):
    """List MCP servers."""
    import httpx

    try:
        servers = httpx.get(f"{server_url}/mcp-servers").json()
        if not servers:
            console.print("[dim]No MCP servers configured[/dim]")
            return

        table = Table(title="MCP Servers")
        table.add_column("Name")
        table.add_column("Transport")
        table.add_column("Command/URL")
        for s in servers:
            table.add_row(
                s["name"],
                s["transport"],
                s.get("command") or s.get("url") or "",
            )
        console.print(table)

    except httpx.HTTPError as e:
        console.print(f"[red]Cannot reach server: {e}[/red]")


@mcp_app.command("remove")
def mcp_remove(
    name: str = typer.Argument(help="MCP server name"),
    server_url: str = typer.Option(
        DEFAULT_URL, "--server", help="Crow server URL"
    ),
):
    """Remove an MCP server."""
    import httpx

    resp = httpx.delete(f"{server_url}/mcp-servers/{name}")
    resp.raise_for_status()
    console.print(f"[green]Removed:[/green] {name}")


# -- Settings subcommands --


@settings_app.command("import")
def settings_import(
    path: str = typer.Argument(
        "crow.yml", help="Path to crow.yml config file"
    ),
    server_url: str = typer.Option(
        DEFAULT_URL, "--server", help="Crow server URL"
    ),
):
    """Import crow.yml into the database."""
    import httpx

    with open(path) as f:
        body = f.read()

    resp = httpx.post(
        f"{server_url}/settings/import",
        content=body,
        headers={"Content-Type": "application/yaml"},
    )
    resp.raise_for_status()
    console.print(f"[green]Imported config from {path}[/green]")


@settings_app.command("export")
def settings_export(
    server_url: str = typer.Option(
        DEFAULT_URL, "--server", help="Crow server URL"
    ),
):
    """Export current config as YAML."""
    import httpx
    import yaml

    resp = httpx.get(f"{server_url}/settings/export")
    resp.raise_for_status()
    console.print(yaml.dump(resp.json(), default_flow_style=False))


if __name__ == "__main__":
    app()
