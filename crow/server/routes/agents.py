from fastapi import APIRouter, Request

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
async def agent_knowledge(name: str, request: Request, category: str | None = None):
    """Get PARA knowledge for an agent."""
    db = request.app.state.db
    entries = await db.search_knowledge(agent_name=name, category=category)
    return entries
