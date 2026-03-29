"""Store tools: store_list, store_get, store_set, store_update, store_delete."""

import httpx

from crow.worker.tools import ToolContext, builtin_tool


@builtin_tool(
    name="store_get",
    description=(
        "Read structured data from the agent store. "
        "Returns the JSON value for a key, or 'not found'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Key to read",
            },
            "namespace": {
                "type": "string",
                "description": "Namespace (defaults to current agent name)",
            },
        },
        "required": ["key"],
    },
)
async def _handle_store_get(inp: dict, ctx: ToolContext) -> str:
    ns = inp.get("namespace") or ctx.job.get("agent_name", "default")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ctx.server_url}/api/store/{ns}/{inp['key']}",
            headers=ctx.headers,
            timeout=10,
        )
        return resp.text


@builtin_tool(
    name="store_set",
    description=(
        "Write structured data to the agent store. "
        "Persists across runs. Use for leads, state, findings, etc."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Key to write",
            },
            "data": {
                "type": "object",
                "description": "JSON data to store",
            },
            "namespace": {
                "type": "string",
                "description": "Namespace (defaults to current agent name)",
            },
        },
        "required": ["key", "data"],
    },
)
async def _handle_store_set(inp: dict, ctx: ToolContext) -> str:
    ns = inp.get("namespace") or ctx.job.get("agent_name", "default")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ctx.server_url}/api/store/{ns}/{inp['key']}",
            headers=ctx.headers,
            json={"data": inp["data"]},
            timeout=10,
        )
        return resp.text


@builtin_tool(
    name="store_append",
    description=(
        "Atomically append items to an array in the store. "
        "Creates the key if it doesn't exist. Use this to save "
        "results incrementally — e.g. append new leads as you find them."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Key containing the array",
            },
            "items": {
                "type": "array",
                "description": "Items to append",
            },
            "namespace": {
                "type": "string",
                "description": "Namespace (defaults to current agent name)",
            },
        },
        "required": ["key", "items"],
    },
)
async def _handle_store_append(inp: dict, ctx: ToolContext) -> str:
    ns = inp.get("namespace") or ctx.job.get("agent_name", "default")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ctx.server_url}/api/store/{ns}/{inp['key']}/append",
            headers=ctx.headers,
            json={"items": inp["items"]},
            timeout=10,
        )
        return resp.text


@builtin_tool(
    name="store_update",
    description=(
        "Partially update a value in the agent store using a dot-notation "
        "path. Example: path='leads.0.status', value='applied'"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Key to update",
            },
            "path": {
                "type": "string",
                "description": "Dot-notation path (e.g. 'leads.0.status')",
            },
            "value": {
                "description": "New value at the path",
            },
            "namespace": {
                "type": "string",
                "description": "Namespace (defaults to current agent name)",
            },
        },
        "required": ["key", "path", "value"],
    },
)
async def _handle_store_update(inp: dict, ctx: ToolContext) -> str:
    ns = inp.get("namespace") or ctx.job.get("agent_name", "default")
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{ctx.server_url}/api/store/{ns}/{inp['key']}",
            headers=ctx.headers,
            json={"path": inp["path"], "value": inp["value"]},
            timeout=10,
        )
        return resp.text


@builtin_tool(
    name="store_delete",
    description="Delete a key from the agent store.",
    input_schema={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Key to delete",
            },
            "namespace": {
                "type": "string",
                "description": "Namespace (defaults to current agent name)",
            },
        },
        "required": ["key"],
    },
)
async def _handle_store_delete(inp: dict, ctx: ToolContext) -> str:
    ns = inp.get("namespace") or ctx.job.get("agent_name", "default")
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{ctx.server_url}/api/store/{ns}/{inp['key']}",
            headers=ctx.headers,
            timeout=10,
        )
        return resp.text


@builtin_tool(
    name="store_list",
    description=(
        "List all keys in the agent store. Call this at the start of a "
        "run to discover what data has been saved from previous runs."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "namespace": {
                "type": "string",
                "description": "Namespace (defaults to current agent name)",
            },
        },
    },
)
async def _handle_store_list(inp: dict, ctx: ToolContext) -> str:
    ns = inp.get("namespace") or ctx.job.get("agent_name", "default")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ctx.server_url}/api/store/{ns}",
            headers=ctx.headers,
            timeout=10,
        )
        return resp.text
