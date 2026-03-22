"""Load crow.yml and import into DB."""

import logging
from pathlib import Path
from typing import Any

import yaml

from crow.db.database import Database

logger = logging.getLogger(__name__)


def parse_config(path: str | Path) -> dict[str, Any]:
    """Parse crow.yml and return the config dict."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f) or {}


async def import_config(db: Database, config: dict[str, Any]) -> None:
    """Import a parsed config dict into the database."""
    agents = config.get("agents", {})
    mcp = config.get("mcp", {})

    for name, server in mcp.items():
        await db.upsert_mcp_server(name=name, url=server["url"])
        logger.info("Imported MCP server: %s → %s", name, server["url"])

    for name, agent in agents.items():
        await db.upsert_agent_def(
            name=name,
            description=agent["description"],
            prompt_template=agent["prompt"],
            tools=agent.get("tools", []),
            mcp_servers=agent.get("mcp", []),
            knowledge_areas=agent.get("knowledge_areas", []),
        )
        logger.info("Imported agent: %s", name)


async def export_config(db: Database) -> dict[str, Any]:
    """Export current DB config as a dict (for YAML output)."""
    agents = {}
    for a in await db.list_agent_defs():
        agents[a["name"]] = {
            "description": a["description"],
            "prompt": a["prompt_template"],
            "tools": list(a["tools"]) if a["tools"] else [],
            "mcp": list(a["mcp_servers"]) if a["mcp_servers"] else [],
            "knowledge_areas": (
                list(a["knowledge_areas"]) if a["knowledge_areas"] else []
            ),
        }

    mcp = {}
    for s in await db.list_mcp_servers():
        mcp[s["name"]] = {"url": s["url"]}

    return {"agents": agents, "mcp": mcp}


async def auto_import_if_empty(db: Database, config_path: str = "crow.yml") -> None:
    """Auto-import crow.yml on first startup if DB has no agents."""
    existing = await db.list_agent_defs()
    if existing:
        return

    path = Path(config_path)
    if not path.exists():
        logger.info("No crow.yml found and no agents in DB")
        return

    logger.info("DB empty — auto-importing from %s", path)
    config = parse_config(path)
    await import_config(db, config)
