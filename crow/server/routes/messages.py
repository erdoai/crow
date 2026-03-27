import base64

from fastapi import APIRouter, Request, UploadFile

from crow.auth.dependencies import get_current_user

router = APIRouter()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB per file


@router.post("/messages")
async def inbound_message(request: Request):
    """Receive a message via the API gateway. Supports JSON or multipart with file attachments."""
    user = await get_current_user(request)
    user_id = user["id"] if user and user["id"] != "default" else None

    content_type = request.headers.get("content-type", "")
    attachments = []

    background = False

    if "multipart/form-data" in content_type:
        form = await request.form()
        text = form.get("text", "")
        thread_id = form.get("thread_id", "default")
        agent = form.get("agent") or None
        background = form.get("background") in ("true", "1", True)

        for key, value in form.multi_items():
            if key == "files" and isinstance(value, UploadFile):
                file_bytes = await value.read()
                if len(file_bytes) > MAX_FILE_SIZE:
                    continue
                attachments.append({
                    "filename": value.filename or "unnamed",
                    "content_type": value.content_type or "application/octet-stream",
                    "data": base64.b64encode(file_bytes).decode("ascii"),
                    "size_bytes": len(file_bytes),
                })
    else:
        body = await request.json()
        text = body["text"]
        thread_id = body.get("thread_id", "default")
        agent = body.get("agent")
        background = body.get("background", False)

    api_gateway = request.app.state.api_gateway
    await api_gateway.handle_inbound(
        gateway_thread_id=thread_id,
        text=text,
        agent=agent,
        user_id=user_id,
        attachments=attachments or None,
        mode="background" if background else None,
    )
    return {"status": "accepted", "thread_id": thread_id}
