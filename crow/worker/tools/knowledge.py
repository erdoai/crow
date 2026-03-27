"""Knowledge tools: knowledge_search, knowledge_write, knowledge_archive."""

import httpx

from crow.worker.tools import ToolContext, builtin_tool


@builtin_tool(
    name="knowledge_search",
    description="Search PARA knowledge base via semantic + keyword.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "category": {
                "type": "string",
                "enum": ["project", "area", "resource", "archive"],
            },
        },
        "required": ["query"],
    },
)
async def _handle_knowledge_search(inp: dict, ctx: ToolContext) -> str:
    async with httpx.AsyncClient() as client:
        params = {
            k: v
            for k, v in {"category": inp.get("category")}.items()
            if v
        }
        resp = await client.get(
            f"{ctx.server_url}/agents/{ctx.job['agent_name']}/knowledge",
            headers=ctx.headers,
            params=params,
            timeout=10,
        )
        return resp.text


@builtin_tool(
    name="knowledge_write",
    description="Save a learning to PARA knowledge base.",
    input_schema={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": ["project", "area", "resource"],
            },
            "title": {"type": "string"},
            "content": {"type": "string"},
            "source_type": {
                "type": "string",
                "enum": ["url", "file", "agent", "user"],
                "description": "Type of source (url, file, agent, user)",
            },
            "source_ref": {
                "type": "string",
                "description": (
                    "Source reference — a URL, filename, etc. "
                    "URLs must be verified reachable before saving."
                ),
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["category", "title", "content"],
    },
)
async def _handle_knowledge_write(inp: dict, ctx: ToolContext) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ctx.server_url}/agents/{ctx.job['agent_name']}/knowledge",
            headers=ctx.headers,
            json={
                "category": inp["category"],
                "title": inp["title"],
                "content": inp["content"],
                "tags": inp.get("tags", []),
                "source_type": inp.get("source_type"),
                "source_ref": inp.get("source_ref"),
            },
            timeout=10,
        )
        return resp.text


@builtin_tool(
    name="knowledge_archive",
    description="Archive a knowledge entry.",
    input_schema={
        "type": "object",
        "properties": {
            "knowledge_id": {"type": "string"},
        },
        "required": ["knowledge_id"],
    },
)
async def _handle_knowledge_archive(inp: dict, ctx: ToolContext) -> str:
    async with httpx.AsyncClient() as client:
        kid = inp["knowledge_id"]
        resp = await client.post(
            f"{ctx.server_url}/agents/{ctx.job['agent_name']}"
            f"/knowledge/{kid}/archive",
            headers=ctx.headers,
            timeout=10,
        )
        return resp.text
