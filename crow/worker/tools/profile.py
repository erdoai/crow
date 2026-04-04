"""Profile tools: let the personal agent update its own name and user profile."""

import httpx

from crow.worker.tools import ToolContext, builtin_tool


@builtin_tool(
    name="set_agent_name",
    description=(
        "Update your own name. Call this when you and the user"
        " agree on what they should call you."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Your new name",
            },
        },
        "required": ["name"],
    },
)
async def _handle_set_agent_name(inp: dict, ctx: ToolContext) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{ctx.server_url}/user/agent",
            json={"agent_name": inp["name"]},
            headers=ctx.headers,
            timeout=10,
        )
        return resp.text


@builtin_tool(
    name="set_user_name",
    description=(
        "Set the user's display name. Call this when you learn"
        " what the user wants to be called."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The user's name/nickname",
            },
        },
        "required": ["name"],
    },
)
async def _handle_set_user_name(inp: dict, ctx: ToolContext) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{ctx.server_url}/user/profile",
            json={"display_name": inp["name"]},
            headers=ctx.headers,
            timeout=10,
        )
        return resp.text
