"""CLI entry point — Typer app."""

import asyncio
import logging

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from crow.config.settings import Settings

app = typer.Typer(name="crow", help="Agent coordination and monitoring system.")
console = Console()


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8100, help="Port to bind to"),
):
    """Start the crow server."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    uvicorn.run(
        "crow.server.app:create_app",
        host=host,
        port=port,
        factory=True,
    )


@app.command()
def worker(
    server_url: str = typer.Option("http://localhost:8100", "--url", help="Crow server URL"),
):
    """Start a crow worker that polls the server for jobs."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    from crow.worker.loop import worker_loop

    settings = Settings()
    asyncio.run(worker_loop(server_url, settings))


@app.command()
def message(
    agent: str = typer.Argument(help="Agent name (pa, monitor, planner, reviewer)"),
    text: str = typer.Argument(help="Message text"),
    server_url: str = typer.Option("http://localhost:8100", "--url", help="Crow server URL"),
):
    """Send a message to an agent (via API gateway)."""
    import httpx

    resp = httpx.post(
        f"{server_url}/messages",
        json={"text": text, "thread_id": f"cli-{agent}"},
    )
    resp.raise_for_status()
    console.print(f"[green]Message sent to {agent}[/green]: {text}")


@app.command()
def status(
    server_url: str = typer.Option("http://localhost:8100", "--url", help="Crow server URL"),
):
    """Show system status."""
    import httpx

    try:
        # Agents
        agents = httpx.get(f"{server_url}/agents").json()
        table = Table(title="Agents")
        table.add_column("Name")
        table.add_column("Description")
        for a in agents:
            table.add_row(a["name"], a["description"])
        console.print(table)

        # Workers
        workers = httpx.get(f"{server_url}/workers").json()
        if workers:
            wtable = Table(title="Workers")
            wtable.add_column("ID")
            wtable.add_column("Name")
            wtable.add_column("Status")
            wtable.add_column("Last Heartbeat")
            for w in workers:
                wtable.add_row(w["id"], w.get("name", ""), w["status"], str(w["last_heartbeat"]))
            console.print(wtable)
        else:
            console.print("[yellow]No workers connected[/yellow]")

    except httpx.HTTPError as e:
        console.print(f"[red]Cannot reach server: {e}[/red]")


@app.command(name="jobs")
def list_jobs(
    status_filter: str | None = typer.Option(None, "--status", help="Filter by status"),
    server_url: str = typer.Option("http://localhost:8100", "--url", help="Crow server URL"),
):
    """List recent jobs."""
    import httpx

    try:
        console.print("[yellow]Jobs listing coming soon[/yellow]")

    except httpx.HTTPError as e:
        console.print(f"[red]Cannot reach server: {e}[/red]")


if __name__ == "__main__":
    app()
