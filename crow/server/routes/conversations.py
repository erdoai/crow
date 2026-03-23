from fastapi import APIRouter, HTTPException, Request

from crow.auth.dependencies import get_current_user

router = APIRouter()


def _user_id_from_request(request, user):
    """Extract scoped user_id when auth is enabled."""
    auth_enabled = request.app.state.auth_config.get("enabled", True)
    if auth_enabled and user and user["id"] != "default":
        return user["id"]
    return None


async def _verify_conversation_access(request, conversation_id, user):
    """Verify the user owns this conversation. Raises 404 if not."""
    db = request.app.state.db
    conv = await db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    uid = _user_id_from_request(request, user)
    if uid and conv.get("user_id") and conv["user_id"] != uid:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.get("/conversations")
async def list_conversations(request: Request):
    db = request.app.state.db
    user = await get_current_user(request)
    uid = _user_id_from_request(request, user)
    return await db.list_conversations(user_id=uid, exclude_delegates=True)


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str, request: Request):
    user = await get_current_user(request)
    await _verify_conversation_access(request, conversation_id, user)
    db = request.app.state.db
    return await db.get_messages(conversation_id)
