"""Web browsing tool: browse_web."""

import asyncio
import logging
import os
from typing import Any

import httpx

from crow.worker.tools import ToolContext, builtin_tool

logger = logging.getLogger(__name__)


@builtin_tool(
    name="browse_web",
    description=(
        "Browse the web using a cloud browser. Provide a natural-language "
        "task and an optional starting URL. A real browser will navigate "
        "pages, click, fill forms, and extract information. Returns the "
        "task output when complete. Use for research, data gathering, "
        "form submission, or any task requiring web interaction."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": (
                    "Natural-language description of what to do in the "
                    "browser (e.g. 'Find the top 5 posts on Hacker News "
                    "and return their titles and URLs')"
                ),
            },
            "start_url": {
                "type": "string",
                "description": (
                    "Optional URL to navigate to before starting the task"
                ),
            },
            "max_steps": {
                "type": "integer",
                "description": (
                    "Maximum browser actions to take (default 10)"
                ),
            },
        },
        "required": ["task"],
    },
)
async def _handle_browse_web(inp: dict, ctx: ToolContext) -> str:
    api_key = os.environ.get("BROWSERUSE_API_KEY")
    if not api_key:
        return "BROWSERUSE_API_KEY not set in environment"

    base_url = "https://api.browser-use.com/api/v2"
    headers = {
        "X-Browser-Use-API-Key": api_key,
        "Content-Type": "application/json",
    }

    payload: dict[str, Any] = {"task": inp["task"]}
    if inp.get("start_url"):
        payload["startUrl"] = inp["start_url"]
    if inp.get("max_steps"):
        payload["maxSteps"] = inp["max_steps"]

    session_id: str | None = None
    try:
        async with httpx.AsyncClient() as client:
            # Create task
            resp = await client.post(
                f"{base_url}/tasks",
                headers=headers,
                json=payload,
                timeout=30,
            )
            if resp.status_code >= 400:
                return f"Failed to create browser task: {resp.text}"
            task_data = resp.json()
            task_id = task_data["id"]
            session_id = task_data.get("sessionId")

            # Poll until finished (max ~5 minutes)
            for _ in range(60):
                await asyncio.sleep(5)
                resp = await client.get(
                    f"{base_url}/tasks/{task_id}",
                    headers=headers,
                    timeout=30,
                )
                if resp.status_code >= 400:
                    return f"Failed to poll browser task: {resp.text}"
                result = resp.json()
                status = result.get("status")

                if status == "finished":
                    output = result.get("output", "(no output)")
                    success = result.get("success", False)
                    steps = result.get("steps", [])
                    parts = []
                    if not success:
                        parts.append("Task completed but may not have succeeded.")
                    parts.append(f"Output: {output}")
                    if steps:
                        parts.append(f"Steps taken: {len(steps)}")
                    return "\n".join(parts)

                if status in ("stopped", "error"):
                    output = result.get("output", "")
                    return f"Browser task {status}: {output}"

            return "Browser task timed out after 5 minutes"
    except Exception as e:
        return f"Browser task failed: {e}"
    finally:
        if session_id:
            # Stop the browser session to free resources
            asyncio.create_task(_stop_browser_session(base_url, headers, session_id))


async def _stop_browser_session(
    base_url: str, headers: dict, session_id: str
) -> None:
    """Stop a browser-use session after a grace period."""
    await asyncio.sleep(300)  # 5 minute grace period
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{base_url}/sessions/{session_id}",
                headers=headers,
                json={"action": "stop"},
                timeout=10,
            )
            logger.info("Stopped browser session %s", session_id)
    except Exception:
        logger.debug("Failed to stop browser session %s", session_id, exc_info=True)
