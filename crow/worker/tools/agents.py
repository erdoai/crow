"""Agent management tools: upsert_agent, list_agents, delete_agent."""

import httpx

from crow.worker.tools import ToolContext, builtin_tool


@builtin_tool(
    name="upsert_agent",
    description=(
        "Create or update an agent. Use when the user asks"
        " to set up a new agent or modify an existing one."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Agent identifier (lowercase, no spaces)",
            },
            "description": {
                "type": "string",
                "description": "What this agent does",
            },
            "prompt_template": {
                "type": "string",
                "description": "System prompt for the agent",
            },
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Tool names: delegate_to_agent,"
                    " knowledge_search, knowledge_write,"
                    " upsert_agent, list_agents, delete_agent,"
                    " evaluate_run"
                ),
            },
        },
        "required": ["name", "description", "prompt_template"],
    },
)
async def _handle_upsert_agent(inp: dict, ctx: ToolContext) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ctx.server_url}/agents",
            json={
                "name": inp["name"],
                "description": inp["description"],
                "prompt_template": inp.get("prompt_template", ""),
                "tools": inp.get("tools", []),
                "mcp_servers": inp.get("mcp_servers", []),
                "knowledge_areas": inp.get("knowledge_areas", []),
            },
            timeout=10,
        )
        return resp.text


@builtin_tool(
    name="list_agents",
    description=(
        "List all configured agents with their descriptions and tools."
    ),
    input_schema={
        "type": "object",
        "properties": {},
    },
)
async def _handle_list_agents(inp: dict, ctx: ToolContext) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ctx.server_url}/agents",
            timeout=10,
        )
        return resp.text


@builtin_tool(
    name="delete_agent",
    description="Delete an agent by name.",
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Agent name to delete",
            },
        },
        "required": ["name"],
    },
)
async def _handle_delete_agent(inp: dict, ctx: ToolContext) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{ctx.server_url}/agents/{inp['name']}",
            timeout=10,
        )
        return resp.text
