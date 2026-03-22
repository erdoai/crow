"""Tools for querying pilot status."""

import httpx

from crow.agents.tools import tool_def

GET_STATUS_DEF = tool_def(
    name="pilot.get_status",
    description="Get current pilot status — active sessions, approval stats, recent actions.",
    parameters={
        "properties": {},
        "required": [],
    },
)


async def get_status(pilot_url: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{pilot_url}/status", timeout=10)
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        return f"Error querying pilot: {e}"
