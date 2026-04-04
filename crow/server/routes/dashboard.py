"""Dashboard JSON API endpoints for the React SPA."""

import base64

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from crow.auth.api_keys import generate_api_key
from crow.auth.dependencies import get_current_user

router = APIRouter()


@router.post("/onboarding")
async def onboarding_submit(form: "OnboardingForm", request: Request):
    """Save display name and create personal agent."""
    user = await get_current_user(request)
    if not user or user["id"] == "default":
        raise HTTPException(status_code=401)

    db = request.app.state.db
    await db.update_user_display_name(user["id"], form.display_name.strip())

    # Create the user's personal agent
    await db.get_or_create_user_agent(user["id"])
    if form.agent_name.strip():
        await db.update_user_agent(
            user["id"],
            agent_name=form.agent_name.strip(),
        )

    return {"status": "ok", "redirect": "/"}


def _uid(request: Request) -> str | None:
    """User ID for DB scoping (set by auth middleware). None = instance-level."""
    return getattr(request.state, "user_id", None)


# -- Personal agent profile --


@router.get("/user/agent")
async def get_user_agent(request: Request):
    """Get the current user's personal agent."""
    user = await get_current_user(request)
    if not user or user["id"] == "default":
        raise HTTPException(status_code=401)
    db = request.app.state.db
    agent = await db.get_or_create_user_agent(user["id"])
    return {
        "agent_name": agent["agent_name"],
        "avatar_url": agent.get("avatar_url"),
    }


class UserProfileUpdate(BaseModel):
    display_name: str


@router.put("/user/profile")
async def update_user_profile(form: UserProfileUpdate, request: Request):
    """Update the current user's display name."""
    user = await get_current_user(request)
    if not user or user["id"] == "default":
        raise HTTPException(status_code=401)
    db = request.app.state.db
    await db.update_user_display_name(user["id"], form.display_name.strip())
    return {"status": "ok", "display_name": form.display_name.strip()}


class UserAgentUpdate(BaseModel):
    agent_name: str | None = None
    avatar_url: str | None = None


@router.put("/user/agent")
async def update_user_agent(form: UserAgentUpdate, request: Request):
    """Update the current user's personal agent."""
    user = await get_current_user(request)
    if not user or user["id"] == "default":
        raise HTTPException(status_code=401)
    db = request.app.state.db
    fields = {k: v for k, v in form.model_dump().items() if v is not None}
    agent = await db.update_user_agent(user["id"], **fields)
    return {
        "agent_name": agent["agent_name"],
        "avatar_url": agent.get("avatar_url"),
    }


@router.get("/skills")
async def list_skills(request: Request):
    """List available skills for the current user."""
    user = await get_current_user(request)
    uid = _uid(request) if user else None
    db = request.app.state.db
    skills = await db.list_skills_for_user(uid)
    return [
        {"name": s["name"], "description": s.get("description", "")}
        for s in skills
    ]


@router.get("/api/dashboard/views")
async def list_views(request: Request):
    """Return dashboard views visible to the current user (own + instance-level)."""
    user_id = _uid(request)

    # File-based views from crow.yml (always instance-level)
    file_views = getattr(request.app.state, "dashboard_config", {}).get("views", {})
    result = [
        {
            "name": name,
            "label": cfg.get("label", name),
            "url": f"/dashboard/custom/{name}/",
            "source": "file",
            "scope": "instance",
        }
        for name, cfg in file_views.items()
    ]

    # DB-stored views (instance-level + user's own)
    db = request.app.state.db
    db_views = await db.list_dashboard_views(user_id=user_id)
    for v in db_views:
        result.append({
            "name": v["name"],
            "label": v["label"],
            "url": f"/dashboard/custom/{v['name']}/",
            "source": "db",
            "scope": "user" if v.get("user_id") else "instance",
            "share_token": v.get("share_token"),
        })

    return result


@router.post("/api/dashboard/views")
async def upload_view(request: Request):
    """Upload a dashboard view.

    Scoped to the authenticated user (or instance-level if static API key).
    """
    user_id = _uid(request)

    db = request.app.state.db
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        name = form.get("name")
        label = form.get("label") or name
        if not name:
            raise HTTPException(status_code=400, detail="name is required")

        files: dict[str, str] = {}
        for key, value in form.multi_items():
            if key == "files" and hasattr(value, "read"):
                upload: UploadFile = value
                content = await upload.read()
                files[upload.filename] = base64.b64encode(content).decode()

        await db.upsert_dashboard_view(str(name), str(label), files, user_id=user_id)
        scope = "user" if user_id else "instance"
        return {"status": "ok", "name": name, "files": len(files), "scope": scope}

    else:
        body = await request.json()
        name = body.get("name")
        label = body.get("label") or name
        files = body.get("files", {})
        if not name:
            raise HTTPException(status_code=400, detail="name is required")

        await db.upsert_dashboard_view(name, label, files, user_id=user_id)
        scope = "user" if user_id else "instance"
        return {"status": "ok", "name": name, "files": len(files), "scope": scope}


@router.delete("/api/dashboard/views/{name}")
async def delete_view(name: str, request: Request):
    """Delete a dashboard view owned by the current user."""
    user_id = _uid(request)

    db = request.app.state.db
    deleted = await db.delete_dashboard_view(name, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="View not found")
    return {"status": "deleted"}


@router.get("/api/dashboard")
async def dashboard_data(request: Request):
    """Return dashboard data as JSON for the SPA."""
    user = await get_current_user(request)
    auth_config = request.app.state.auth_config
    auth_enabled = auth_config.get("enabled", True)

    if not user:
        raise HTTPException(status_code=401)

    db = request.app.state.db
    uid = _uid(request)

    # Personal agent
    user_agent = None
    if auth_enabled and user["id"] != "default":
        ua = await db.get_or_create_user_agent(user["id"])
        user_agent = {
            "agent_name": ua["agent_name"],
            "avatar_url": ua.get("avatar_url"),
        }

    # Skills (agent_defs reinterpreted)
    skills_raw = await db.list_skills_for_user(uid)
    skills = [
        {"name": s["name"], "description": s.get("description", "")}
        for s in skills_raw
    ]

    conversations = await db.list_conversations(
        limit=10, user_id=user["id"] if auth_enabled else None, exclude_delegates=True
    )
    knowledge = await db.search_knowledge(
        user_id=user["id"] if auth_enabled else None, limit=20
    )
    api_keys = await db.list_api_keys(
        user_id=user["id"]
        if auth_enabled and user["id"] != "default"
        else None
    )
    display_name = user.get("display_name") or "User"

    return {
        "user_agent": user_agent,
        "skills": skills,
        "conversations": [
            {
                "id": c["id"],
                "gateway": c.get("gateway", ""),
                "gateway_thread_id": c.get("gateway_thread_id", ""),
                "title": c.get("title"),
                "updated_at": (
                    c["updated_at"].isoformat()
                    if c.get("updated_at")
                    else None
                ),
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
            {
                "id": k["id"],
                "name": k["name"],
                "key_prefix": k["key_prefix"],
            }
            for k in api_keys
        ],
        "display_name": display_name,
        "auth_enabled": auth_enabled,
    }


@router.get("/api/shared/{token}")
async def shared_agent_data(token: str, request: Request):
    """Return shared agent data as JSON (public, no auth required)."""
    db = request.app.state.db
    share = await db.get_agent_share_by_token(token)
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found")

    agent = await db.get_agent_def(share["agent_name"])
    if not agent:
        raise HTTPException(status_code=404, detail="Agent no longer exists")

    return {
        "name": agent["name"],
        "description": agent.get("description", ""),
        "tools": list(agent.get("tools") or []),
        "mcp_servers": list(agent.get("mcp_servers") or []),
        "knowledge_areas": list(agent.get("knowledge_areas") or []),
    }


@router.get("/knowledge")
async def list_knowledge(request: Request):
    """List all knowledge entries for the current user (with full content)."""
    user = await get_current_user(request)
    if not user or user["id"] == "default":
        raise HTTPException(status_code=401)
    db = request.app.state.db
    entries = await db.list_knowledge(user["id"])
    return [
        {
            "id": k["id"],
            "category": k.get("category", ""),
            "title": k.get("title", ""),
            "content": k.get("content", ""),
            "pinned": k.get("pinned", False),
            "updated_at": k["updated_at"].isoformat() if k.get("updated_at") else None,
        }
        for k in entries
    ]


@router.get("/knowledge/{knowledge_id}")
async def get_knowledge_entry(knowledge_id: str, request: Request):
    """Get a single knowledge entry with full content."""
    user = await get_current_user(request)
    if not user or user["id"] == "default":
        raise HTTPException(status_code=401)
    db = request.app.state.db
    entry = await db.get_knowledge_entry(knowledge_id, user_id=user["id"])
    if not entry:
        raise HTTPException(status_code=404)
    return {
        "id": entry["id"],
        "category": entry.get("category", ""),
        "title": entry.get("title", ""),
        "content": entry.get("content", ""),
        "pinned": entry.get("pinned", False),
        "updated_at": entry["updated_at"].isoformat() if entry.get("updated_at") else None,
    }


@router.delete("/knowledge/{knowledge_id}")
async def delete_knowledge(knowledge_id: str, request: Request):
    """Delete a knowledge entry."""
    user = await get_current_user(request)
    if not user or user["id"] == "default":
        raise HTTPException(status_code=401)
    db = request.app.state.db
    deleted = await db.delete_knowledge(knowledge_id, user_id=user["id"])
    if not deleted:
        raise HTTPException(status_code=404)
    return {"status": "deleted"}


class OnboardingForm(BaseModel):
    display_name: str
    agent_name: str = "assistant"


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
