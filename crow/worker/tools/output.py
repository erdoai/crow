"""Common output handling for tool results.

Large outputs are chunked, stored in knowledge (with pgvector embeddings
for semantic search), and a truncated preview is returned to the LLM.
The agent can use knowledge_search to retrieve specific chunks.

Usage from any tool handler:

    from crow.worker.tools.output import process_tool_output

    raw = some_big_result()
    return await process_tool_output(raw, ctx=ctx, tool_name="my_tool")
"""

import hashlib
import logging

import httpx

from crow.worker.tools import ToolContext

logger = logging.getLogger(__name__)

# Results under this go straight to the LLM — no storage needed.
INLINE_LIMIT = 4000

# Each chunk stored in knowledge. Sized for useful semantic search —
# large enough for context, small enough for targeted retrieval.
CHUNK_SIZE = 3000
CHUNK_OVERLAP = 200


def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks for semantic search."""
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        # Try to break at a newline near the end
        if end < len(text):
            newline = text.rfind("\n", start + CHUNK_SIZE - 500, end)
            if newline > start:
                end = newline + 1
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP
    return chunks


async def process_tool_output(
    output: str,
    *,
    ctx: ToolContext,
    tool_name: str,
    title: str | None = None,
) -> str:
    """Return output directly if small, or chunk + store + return preview."""
    if not output or len(output) <= INLINE_LIMIT:
        return output

    content_hash = hashlib.md5(output[:500].encode()).hexdigest()[:8]
    ref_title = title or f"{tool_name} output ({content_hash})"

    # Chunk and store in knowledge for semantic search
    chunks = _chunk_text(output)
    stored = 0
    try:
        async with httpx.AsyncClient() as client:
            for i, chunk in enumerate(chunks):
                chunk_title = (
                    f"{ref_title} [{i + 1}/{len(chunks)}]"
                    if len(chunks) > 1
                    else ref_title
                )
                resp = await client.post(
                    f"{ctx.server_url}/agents/{ctx.job['agent_name']}/knowledge",
                    headers=ctx.headers,
                    json={
                        "category": "resource",
                        "title": chunk_title,
                        "content": chunk,
                        "tags": ["tool-output", tool_name],
                        "source_type": "agent",
                        "source_ref": f"tool:{tool_name}:{content_hash}",
                    },
                    timeout=15,
                )
                if resp.status_code < 300:
                    stored += 1
    except Exception:
        logger.warning("Failed to store tool output for %s", tool_name)

    preview = output[:INLINE_LIMIT]
    if stored:
        return (
            f"{preview}\n\n"
            f"... ({len(output):,} chars, {stored} chunks stored in knowledge "
            f"as \"{ref_title}\". Use knowledge_search to query specific parts.)"
        )
    # Storage failed — return what we can
    return f"{preview}\n\n... ({len(output):,} chars total, truncated)"
