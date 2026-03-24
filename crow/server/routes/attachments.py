"""Attachment endpoints — download files attached to messages."""

import base64

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

router = APIRouter(prefix="/attachments")


@router.get("/{attachment_id}/download")
async def download_attachment(attachment_id: str, request: Request):
    """Download an attachment by ID."""
    db = request.app.state.db
    att = await db.get_attachment(attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")

    content = base64.b64decode(att["data"])
    return Response(
        content=content,
        media_type=att["content_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{att["filename"]}"',
        },
    )
