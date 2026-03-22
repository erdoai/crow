from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


@router.get("/agents")
async def list_agents(request: Request):
    """List all registered agents."""
    registry = request.app.state.registry
    return [
        {"name": a.name, "description": a.description}
        for a in registry.list()
    ]


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
