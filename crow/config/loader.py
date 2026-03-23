"""Load crow.yml and import into DB."""

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from crow.db.database import Database

logger = logging.getLogger(__name__)

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")

AUTH_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "session_secret": "dev-secret-change-in-prod",
    "api_key": "",
    "resend": {
        "api_key": "",
        "from": os.environ.get("RESEND_FROM", "crow <noreply@erdo.ai>"),
    },
}


def _resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ${VAR} references from environment."""
    if isinstance(value, str):
        return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(v) for v in value]
    return value


def _deep_merge(defaults: dict, overrides: dict) -> dict:
    """Merge overrides into defaults, recursing into nested dicts."""
    result = dict(defaults)
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def extract_auth_config(config: dict[str, Any]) -> dict[str, Any]:
    """Extract auth section from config with defaults applied."""
    raw = config.get("auth", {}) or {}
    return _deep_merge(AUTH_DEFAULTS, raw)


DASHBOARD_DEFAULTS: dict[str, Any] = {"views": {}}


def extract_dashboard_config(config: dict[str, Any]) -> dict[str, Any]:
    """Extract dashboard section from config with defaults applied."""
    raw = config.get("dashboard", {}) or {}
    return _deep_merge(DASHBOARD_DEFAULTS, raw)


def parse_config(path: str | Path) -> dict[str, Any]:
    """Parse crow.yml, resolve ${VAR} env references, and return config dict."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return _resolve_env_vars(raw)


async def import_config(db: Database, config: dict[str, Any]) -> None:
    """Import a parsed config dict into the database."""
    agents = config.get("agents", {})
    mcp = config.get("mcp", {})

    for name, server in mcp.items():
        await db.upsert_mcp_server(
            name=name, url=server["url"], headers=server.get("headers", {})
        )
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
        entry: dict = {"url": s["url"]}
        headers = s.get("headers")
        if headers:
            entry["headers"] = headers
        mcp[s["name"]] = entry

    return {"agents": agents, "mcp": mcp}


def _parse_yaml_string(raw_yaml: str) -> dict[str, Any]:
    """Parse a YAML string and resolve env vars."""
    raw = yaml.safe_load(raw_yaml) or {}
    return _resolve_env_vars(raw)


def load_config(config_path: str = "crow.yml") -> dict[str, Any]:
    """Load config from CROW_CONFIG env var or crow.yml file."""
    # Prefer CROW_CONFIG env var (for deployments where file isn't available)
    config_env = os.environ.get("CROW_CONFIG", "")
    if config_env:
        logger.info("Loading config from CROW_CONFIG env var")
        return _parse_yaml_string(config_env)

    path = Path(config_path)
    if not path.exists():
        logger.info("No crow.yml found at %s", path)
        return {}
    return parse_config(path)


async def auto_import_if_empty(db: Database, config_path: str = "crow.yml") -> None:
    """Auto-import config on first startup if DB has no agents."""
    existing = await db.list_agent_defs()
    if existing:
        return

    config = load_config(config_path)
    if not config:
        logger.info("No config found — no agents to import")
        return

    logger.info("DB empty — auto-importing config")
    await import_config(db, config)
