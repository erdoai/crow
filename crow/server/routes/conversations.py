from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/conversations")
async def list_conversations(request: Request):
    db = request.app.state.db
    return await db.list_conversations()


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str, request: Request):
    db = request.app.state.db
    return await db.get_messages(conversation_id)
