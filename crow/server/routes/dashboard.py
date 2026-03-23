"""Dashboard JSON API endpoints for the React SPA."""

import base64

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from crow.auth.api_keys import generate_api_key
from crow.auth.dependencies import get_current_user

router = APIRouter()


@router.post("/onboarding")
async def onboarding_submit(form: "OnboardingForm", request: Request):
    """Save display name."""
    user = await get_current_user(request)
    if not user or user["id"] == "default":
        raise HTTPException(status_code=401)

    db = request.app.state.db
    await db.update_user_display_name(user["id"], form.display_name.strip())
    return {"status": "ok", "redirect": "/dashboard"}


@router.get("/api/dashboard/views")
async def list_views(request: Request):
    """Return configured custom dashboard views (file-based + DB-stored)."""
    # File-based views from crow.yml
    file_views = getattr(request.app.state, "dashboard_config", {}).get("views", {})
    result = [
        {
            "name": name,
            "label": cfg.get("label", name),
            "url": f"/dashboard/custom/{name}/",
            "source": "file",
        }
        for name, cfg in file_views.items()
    ]

    # DB-stored views
    db = request.app.state.db
    db_views = await db.list_dashboard_views()
    for v in db_views:
        result.append({
            "name": v["name"],
            "label": v["label"],
            "url": f"/dashboard/custom/{v['name']}/",
            "source": "db",
        })

    return result


@router.post("/api/dashboard/views")
async def upload_view(request: Request):
    """Upload a dashboard view. Accepts multipart form or JSON."""
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

        await db.upsert_dashboard_view(str(name), str(label), files)
        return {"status": "ok", "name": name, "files": len(files)}

    else:
        body = await request.json()
        name = body.get("name")
        label = body.get("label") or name
        files = body.get("files", {})
        if not name:
            raise HTTPException(status_code=400, detail="name is required")

        await db.upsert_dashboard_view(name, label, files)
        return {"status": "ok", "name": name, "files": len(files)}


@router.delete("/api/dashboard/views/{name}")
async def delete_view(name: str, request: Request):
    """Delete a DB-stored dashboard view."""
    db = request.app.state.db
    deleted = await db.delete_dashboard_view(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="View not found")
    return {"status": "deleted"}


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
        user_id=user["id"]
        if auth_enabled and user["id"] != "default"
        else None
    )
    display_name = user.get("display_name") or "User"

    return {
        "agents": [
            {"name": a["name"], "description": a.get("description", "")}
            for a in agents
        ],
        "conversations": [
            {
                "id": c["id"],
                "gateway": c.get("gateway", ""),
                "gateway_thread_id": c.get("gateway_thread_id", ""),
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


class OnboardingForm(BaseModel):
    display_name: str


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
