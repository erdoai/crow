"""Config routes — MCP servers, settings import/export."""

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from crow.config.loader import export_config, import_config

router = APIRouter()


# -- MCP Servers --


class MCPServerCreate(BaseModel):
    name: str
    transport: str = "stdio"
    command: str | None = None
    url: str | None = None
    env: dict | None = None


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
    await db.upsert_mcp_server(
        name=body.name,
        transport=body.transport,
        command=body.command,
        url=body.url,
        env=body.env,
    )
    return {"status": "ok", "name": body.name}


@router.delete("/mcp-servers/{name}")
async def delete_mcp_server(name: str, request: Request):
    db = request.app.state.db
    await db.delete_mcp_server(name)
    return {"status": "deleted", "name": name}


# -- Settings import/export --


@router.post("/settings/import")
async def import_settings(request: Request):
    """Import crow.yml config from request body (YAML string)."""
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
