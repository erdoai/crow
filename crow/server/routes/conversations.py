from fastapi import APIRouter, Request

from crow.auth.dependencies import get_current_user

router = APIRouter()


@router.get("/conversations")
async def list_conversations(request: Request):
    db = request.app.state.db
    auth_enabled = request.app.state.auth_config.get("enabled", True)
    user = await get_current_user(request)
    user_id = user["id"] if auth_enabled and user and user["id"] != "default" else None
    return await db.list_conversations(user_id=user_id, exclude_delegates=True)


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str, request: Request):
    db = request.app.state.db
    return await db.get_messages(conversation_id)
