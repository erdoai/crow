"""Config routes — MCP servers, settings import/export."""

import yaml
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from crow.config.loader import export_config, import_config

router = APIRouter()


def _check_admin_key(request: Request, x_worker_key: str) -> None:
    """Settings import requires the worker API key (admin-level access)."""
    expected = request.app.state.settings.worker_api_key
    if x_worker_key != expected:
        raise HTTPException(status_code=401, detail="Admin access required")


# -- MCP Servers --


class MCPServerCreate(BaseModel):
    name: str
    url: str
    headers: dict = {}


@router.get("/mcp-servers")
async def list_mcp_servers(request: Request):
    db = request.app.state.db
    return await db.list_mcp_servers()


@router.get("/mcp-servers/{name}")
async def get_mcp_server(name: str, request: Request):
    db = request.app.state.db
    server = await db.get_mcp_server(name)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return server


@router.post("/mcp-servers")
async def create_mcp_server(body: MCPServerCreate, request: Request):
    db = request.app.state.db
    await db.upsert_mcp_server(name=body.name, url=body.url, headers=body.headers)
    return {"status": "ok", "name": body.name}


@router.delete("/mcp-servers/{name}")
async def delete_mcp_server(name: str, request: Request):
    db = request.app.state.db
    await db.delete_mcp_server(name)
    return {"status": "deleted", "name": name}


# -- Settings import/export --


@router.post("/settings/import")
async def import_settings(request: Request, x_worker_key: str = Header()):
    """Import crow.yml config from request body (YAML string). Requires admin key."""
    _check_admin_key(request, x_worker_key)
    body = await request.body()
    config = yaml.safe_load(body.decode()) or {}
    db = request.app.state.db
    await import_config(db, config)
    return {"status": "imported"}


@router.get("/settings/export")
async def export_settings(request: Request):
    """Export current config as YAML."""
    db = request.app.state.db
    config = await export_config(db)
    return config
