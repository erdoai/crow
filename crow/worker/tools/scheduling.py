"""Scheduling tools: schedule, progress_update, post_update."""

import httpx

from crow.worker.tools import ToolContext, builtin_tool


@builtin_tool(
    name="schedule",
    description=(
        "Schedule a future job. Use for heartbeats (schedule yourself to"
        " run again later) or delayed tasks for any agent."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": (
                    "Agent to run (use your own name for heartbeat)"
                ),
            },
            "input": {
                "type": "string",
                "description": "Message/task for the scheduled run",
            },
            "delay_seconds": {
                "type": "integer",
                "description": "Seconds from now to run (one-shot)",
            },
            "cron": {
                "type": "string",
                "description": (
                    "Cron expression for recurring schedule"
                    " (e.g. '*/5 * * * *'). Mutually exclusive"
                    " with delay_seconds."
                ),
            },
            "replace": {
                "type": "boolean",
                "description": (
                    "Cancel existing active schedules for this"
                    " agent before creating a new one. Use for"
                    " heartbeats to prevent duplicate schedules."
                ),
            },
        },
        "required": ["agent_name", "input"],
    },
)
async def _handle_schedule(inp: dict, ctx: ToolContext) -> str:
    payload = {
        "agent_name": inp["agent_name"],
        "input": inp["input"],
        "conversation_id": ctx.job.get("conversation_id"),
        "user_id": ctx.job.get("user_id"),
        "created_by_job_id": ctx.job.get("id"),
        "replace": inp.get("replace", False),
    }
    if inp.get("cron"):
        payload["cron"] = inp["cron"]
    elif inp.get("delay_seconds"):
        payload["delay_seconds"] = inp["delay_seconds"]
    else:
        payload["delay_seconds"] = 60  # default 1 minute

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ctx.server_url}/scheduled-jobs",
            headers=ctx.headers,
            json=payload,
            timeout=10,
        )
        if resp.status_code >= 400:
            return f"Schedule failed: {resp.text}"
        data = resp.json()
        if inp.get("cron"):
            kind = f"cron={inp['cron']}"
        else:
            kind = f"in {payload.get('delay_seconds')}s"
        return (
            f"Scheduled {inp['agent_name']} ({kind}), id={data['id']}"
        )


@builtin_tool(
    name="progress_update",
    description=(
        "Publish a progress update visible to dashboards"
        " in real-time via SSE."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "Human-readable status message",
            },
            "data": {
                "type": "object",
                "description": (
                    "Optional structured data (progress %, metrics, etc.)"
                ),
            },
        },
        "required": ["status"],
    },
)
async def _handle_progress_update(inp: dict, ctx: ToolContext) -> str:
    job_id = ctx.job.get("id", "unknown")
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{ctx.server_url}/jobs/{job_id}/progress",
            headers=ctx.headers,
            json={
                "status": inp["status"],
                "data": inp.get("data"),
                "agent_name": ctx.job.get("agent_name"),
            },
            timeout=10,
        )
        return f"Progress published: {inp['status']}"


@builtin_tool(
    name="post_update",
    description=(
        "Post a message to the conversation thread. Use during background "
        "runs to share important findings. Use sparingly — only when you "
        "have something worth reporting."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Message to post to the thread",
            },
        },
        "required": ["text"],
    },
)
async def _handle_post_update(inp: dict, ctx: ToolContext) -> str:
    job_id = ctx.job.get("id", "unknown")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ctx.server_url}/jobs/{job_id}/update-message",
            headers=ctx.headers,
            json={
                "text": inp["text"],
                "agent_name": ctx.job.get("agent_name"),
            },
            timeout=10,
        )
        if resp.status_code >= 400:
            return f"Failed to post update: {resp.text}"
        return "Update posted to conversation."
