"""Common output handling for tool results.

Large outputs are stored in knowledge (with embeddings for semantic
search) and a truncated preview is returned to the LLM. The agent can
use knowledge_search to retrieve specific parts of the full output.
"""

import hashlib

import httpx

from crow.worker.tools import ToolContext

# Results under this threshold go straight to the LLM.
PREVIEW_CHARS = 4000
# Results over this get stored in knowledge + truncated preview.
STORE_THRESHOLD = PREVIEW_CHARS


async def process_tool_output(
    output: str,
    *,
    ctx: ToolContext,
    tool_name: str,
    title: str | None = None,
) -> str:
    """Return output directly if small, or store + return preview if large."""
    if len(output) <= STORE_THRESHOLD:
        return output

    preview = output[:PREVIEW_CHARS]
    content_hash = hashlib.md5(output[:500].encode()).hexdigest()[:8]
    ref_title = title or f"{tool_name} output ({content_hash})"

    # Store full output in knowledge for semantic search
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{ctx.server_url}/agents/{ctx.job['agent_name']}/knowledge",
                headers=ctx.headers,
                json={
                    "category": "resource",
                    "title": ref_title,
                    "content": output,
                    "tags": ["tool-output", tool_name],
                    "source_type": "agent",
                    "source_ref": f"tool:{tool_name}",
                },
                timeout=15,
            )
    except Exception:
        # If storage fails, just return truncated output
        return output[:PREVIEW_CHARS] + (
            f"\n\n... ({len(output)} chars total, storage failed — "
            f"output truncated)"
        )

    return (
        f"{preview}\n\n"
        f"... ({len(output)} chars total — truncated. Full output saved "
        f"to knowledge as \"{ref_title}\". Use knowledge_search to find "
        f"specific details.)"
    )
