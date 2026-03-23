import secrets

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from crow.agents.format import agent_to_markdown, markdown_to_agent

router = APIRouter()


# -- CRUD --


@router.get("/agents")
async def list_agents(request: Request):
    """List all registered agents."""
    db = request.app.state.db
    return await db.list_agent_defs()


@router.get("/agents/{name}")
async def get_agent(name: str, request: Request):
    """Get a single agent definition."""
    db = request.app.state.db
    agent = await db.get_agent_def(name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


class AgentUpsert(BaseModel):
    name: str
    description: str = ""
    prompt_template: str = ""
    tools: list[str] = []
    mcp_servers: list[str] = []
    knowledge_areas: list[str] = []


@router.post("/agents")
async def create_or_update_agent(agent: AgentUpsert, request: Request):
    """Create or update an agent definition."""
    db = request.app.state.db
    await db.upsert_agent_def(
        name=agent.name,
        description=agent.description,
        prompt_template=agent.prompt_template,
        tools=agent.tools,
        mcp_servers=agent.mcp_servers,
        knowledge_areas=agent.knowledge_areas,
    )
    return {"status": "ok", "name": agent.name}


@router.delete("/agents/{name}")
async def delete_agent(name: str, request: Request):
    """Delete an agent definition."""
    db = request.app.state.db
    agent = await db.get_agent_def(name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete_agent_def(name)
    return {"status": "deleted", "name": name}


# -- Export / Import --


@router.get("/agents/{name}/export")
async def export_agent(name: str, request: Request):
    """Export a single agent as markdown with YAML frontmatter."""
    db = request.app.state.db
    agent = await db.get_agent_def(name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    md = agent_to_markdown(agent)
    return PlainTextResponse(
        md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{name}.md"'},
    )


@router.post("/agents/import")
async def import_agent(request: Request):
    """Import an agent from markdown (YAML frontmatter + prompt body)."""
    body = await request.body()
    content = body.decode("utf-8")

    try:
        agent_data = markdown_to_agent(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db = request.app.state.db
    await db.upsert_agent_def(
        name=agent_data["name"],
        description=agent_data["description"],
        prompt_template=agent_data["prompt_template"],
        tools=agent_data["tools"],
        mcp_servers=agent_data["mcp_servers"],
        knowledge_areas=agent_data["knowledge_areas"],
    )
    return {"status": "imported", "name": agent_data["name"]}


# -- Share links --


@router.post("/agents/{name}/share")
async def create_share_link(name: str, request: Request):
    """Create (or return existing) share link for an agent."""
    db = request.app.state.db
    agent = await db.get_agent_def(name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    existing = await db.get_agent_share(name)
    if existing:
        base = str(request.base_url).rstrip("/")
        return {"token": existing["token"], "url": f"{base}/shared/{existing['token']}"}

    token = secrets.token_urlsafe(16)
    await db.create_agent_share(name, token)
    base = str(request.base_url).rstrip("/")
    return {"token": token, "url": f"{base}/shared/{token}"}


@router.delete("/agents/{name}/share")
async def revoke_share_link(name: str, request: Request):
    """Revoke a share link for an agent."""
    db = request.app.state.db
    await db.delete_agent_share(name)
    return {"status": "revoked", "name": name}


# -- Knowledge --


@router.get("/agents/{name}/knowledge")
async def agent_knowledge(
    name: str, request: Request, category: str | None = None
):
    """Get PARA knowledge for an agent."""
    db = request.app.state.db
    entries = await db.search_knowledge(agent_name=name, category=category)
    return entries


class KnowledgeWrite(BaseModel):
    category: str
    title: str
    content: str
    tags: list[str] = []


@router.post("/agents/{name}/knowledge")
async def write_knowledge(
    name: str,
    entry: KnowledgeWrite,
    request: Request,
    x_worker_key: str = Header(),
):
    """Write a PARA knowledge entry for an agent."""
    settings = request.app.state.settings
    if x_worker_key != settings.worker_api_key:
        raise HTTPException(status_code=401, detail="Invalid worker key")

    db = request.app.state.db
    from crow.agents.knowledge import generate_embedding

    embedding = await generate_embedding(
        f"{entry.title}\n{entry.content}", settings
    )
    knowledge_id = await db.upsert_knowledge(
        agent_name=name,
        category=entry.category,
        title=entry.title,
        content=entry.content,
        source="agent",
        tags=entry.tags,
        embedding=embedding,
    )
    return {"id": knowledge_id}


@router.post("/agents/{name}/knowledge/{knowledge_id}/archive")
async def archive_knowledge(
    name: str,
    knowledge_id: str,
    request: Request,
    x_worker_key: str = Header(),
):
    """Archive a knowledge entry."""
    settings = request.app.state.settings
    if x_worker_key != settings.worker_api_key:
        raise HTTPException(status_code=401, detail="Invalid worker key")

    db = request.app.state.db
    await db.archive_knowledge(knowledge_id)
    return {"status": "archived"}
