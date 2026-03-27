"""File attachment tool: create_attachment."""

import base64

import httpx

from crow.worker.tools import ToolContext, builtin_tool


@builtin_tool(
    name="create_attachment",
    description=(
        "Create a file attachment on your response. Use to send"
        " documents like cover letters, reports, or data files."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": (
                    "Filename with extension"
                    " (e.g. 'cover_letter.md', 'report.csv')"
                ),
            },
            "content": {
                "type": "string",
                "description": "The text content of the file",
            },
            "content_type": {
                "type": "string",
                "description": "MIME type (default: text/plain)",
            },
        },
        "required": ["filename", "content"],
    },
)
async def _handle_create_attachment(inp: dict, ctx: ToolContext) -> str:
    content = inp["content"]
    content_b64 = base64.b64encode(
        content.encode("utf-8")
    ).decode("ascii")
    ct = inp.get("content_type", "text/plain")
    filename = inp["filename"]
    size_bytes = len(content.encode("utf-8"))
    job_id = ctx.job.get("id", "unknown")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ctx.server_url}/jobs/{job_id}/attachments",
            headers=ctx.headers,
            json={
                "filename": filename,
                "content_type": ct,
                "data": content_b64,
                "size_bytes": size_bytes,
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            return f"Failed to create attachment: {resp.text}"
        att_data = resp.json()
        return f"Created attachment: {filename} (id={att_data['id']})"
