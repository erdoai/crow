"""Dashboard routes: login, onboarding, main dashboard, API keys."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from crow.auth.api_keys import generate_api_key
from crow.auth.dependencies import get_current_user

router = APIRouter()

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Redirect to dashboard or login."""
    user = await get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render login page (auth enabled only)."""
    auth_config = request.app.state.auth_config
    if not auth_config.get("enabled", False):
        return RedirectResponse(url="/dashboard", status_code=303)

    # Already logged in?
    user = await get_current_user(request)
    if user and user["id"] != "default":
        return RedirectResponse(url="/dashboard", status_code=303)

    return templates.TemplateResponse(request, "login.html.j2")


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request):
    """Render onboarding page."""
    user = await get_current_user(request)
    if not user or user["id"] == "default":
        return RedirectResponse(url="/login", status_code=303)
    if user.get("display_name"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(request, "onboarding.html.j2", {"user": user})


class OnboardingForm(BaseModel):
    display_name: str


@router.post("/onboarding")
async def onboarding_submit(form: OnboardingForm, request: Request):
    """Save display name and redirect to dashboard."""
    user = await get_current_user(request)
    if not user or user["id"] == "default":
        raise HTTPException(status_code=401)

    db = request.app.state.db
    await db.update_user_display_name(user["id"], form.display_name.strip())
    return {"status": "ok", "redirect": "/dashboard"}


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Render main dashboard."""
    user = await get_current_user(request)
    auth_config = request.app.state.auth_config
    auth_enabled = auth_config.get("enabled", False)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # If auth enabled and no display_name, redirect to onboarding
    if auth_enabled and user["id"] != "default" and not user.get("display_name"):
        return RedirectResponse(url="/onboarding", status_code=303)

    db = request.app.state.db

    agents = await db.list_agent_defs()
    conversations = await db.list_conversations(
        limit=10, user_id=user["id"] if auth_enabled else None
    )
    knowledge = await db.search_knowledge(
        user_id=user["id"] if auth_enabled else None, limit=20
    )
    api_keys = await db.list_api_keys(
        user_id=user["id"] if auth_enabled and user["id"] != "default" else None
    )
    display_name = user.get("display_name") or "User"

    return templates.TemplateResponse(
        request,
        "dashboard.html.j2",
        {
            "user": user,
            "display_name": display_name,
            "auth_enabled": auth_enabled,
            "agents": agents,
            "conversations": conversations,
            "knowledge": knowledge,
            "api_keys": api_keys,

        },
    )


@router.get("/chat", response_class=HTMLResponse)
@router.get("/chat/{conversation_id}", response_class=HTMLResponse)
async def chat_page(request: Request, conversation_id: str | None = None):
    """Render chat page."""
    user = await get_current_user(request)
    auth_config = request.app.state.auth_config
    auth_enabled = auth_config.get("enabled", False)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    db = request.app.state.db
    agents = await db.list_agent_defs()
    conversations = await db.list_conversations(
        limit=50, user_id=user["id"] if auth_enabled else None
    )

    messages = []
    current_thread_id = None
    current_agent = None
    if conversation_id:
        messages = await db.get_messages(conversation_id)
        conv = await db.get_conversation(conversation_id)
        if conv:
            current_thread_id = conv["gateway_thread_id"]

    return templates.TemplateResponse(
        request,
        "chat.html.j2",
        {
            "agents": agents,
            "conversations": conversations,
            "messages": messages,
            "current_conversation_id": conversation_id,
            "current_thread_id": current_thread_id,
            "current_agent": current_agent,
        },
    )


@router.get("/api/dashboard")
async def dashboard_data(request: Request):
    """Return dashboard data as JSON for the SPA."""
    user = await get_current_user(request)
    auth_config = request.app.state.auth_config
    auth_enabled = auth_config.get("enabled", False)

    if not user:
        raise HTTPException(status_code=401)

    db = request.app.state.db

    agents = await db.list_agent_defs()
    conversations = await db.list_conversations(
        limit=10, user_id=user["id"] if auth_enabled else None
    )
    knowledge = await db.search_knowledge(
        user_id=user["id"] if auth_enabled else None, limit=20
    )
    api_keys = await db.list_api_keys(
        user_id=user["id"] if auth_enabled and user["id"] != "default" else None
    )
    display_name = user.get("display_name") or "User"

    return {
        "agents": [{"name": a["name"], "description": a.get("description", "")} for a in agents],
        "conversations": [
            {
                "id": c["id"],
                "gateway": c.get("gateway", ""),
                "gateway_thread_id": c.get("gateway_thread_id", ""),
                "updated_at": c["updated_at"].isoformat() if c.get("updated_at") else None,
            }
            for c in conversations
        ],
        "knowledge": [
            {
                "id": k["id"],
                "category": k.get("category", ""),
                "title": k.get("title", ""),
                "agent_name": k.get("agent_name", ""),
            }
            for k in knowledge
        ],
        "api_keys": [
            {"id": k["id"], "name": k["name"], "key_prefix": k["key_prefix"]}
            for k in api_keys
        ],
        "display_name": display_name,
        "auth_enabled": auth_enabled,
    }


class CreateApiKeyRequest(BaseModel):
    name: str


@router.post("/dashboard/api-keys")
async def create_api_key(form: CreateApiKeyRequest, request: Request):
    """Create a new API key. Returns the full key (shown once)."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)

    db = request.app.state.db
    full_key, key_hash, key_prefix = generate_api_key()
    user_id = user["id"] if user["id"] != "default" else None
    key_id = await db.create_api_key(
        name=form.name.strip(),
        key_hash=key_hash,
        key_prefix=key_prefix,
        user_id=user_id,
    )
    return {"id": key_id, "key": full_key, "prefix": key_prefix}


@router.delete("/dashboard/api-keys/{key_id}")
async def delete_api_key(key_id: str, request: Request):
    """Revoke an API key."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)

    db = request.app.state.db
    user_id = user["id"] if user["id"] != "default" else None
    deleted = await db.delete_api_key(key_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404)
    return {"status": "revoked"}
