"""Delegation tools: delegate_to_agent, delegate_parallel, spawn_job."""

import asyncio
import json

import httpx

from crow.worker.tools import ToolContext, builtin_tool
from crow.worker.tools.output import process_tool_output


@builtin_tool(
    name="delegate_to_agent",
    description="Delegate a task to a specialist agent.",
    input_schema={
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "Agent to delegate to",
            },
            "task": {
                "type": "string",
                "description": "What the agent should do",
            },
        },
        "required": ["agent_name", "task"],
    },
)
async def _handle_delegate_to_agent(inp: dict, ctx: ToolContext) -> str:
    from crow.worker.executor import run_agent

    agent_name = inp["agent_name"]
    task = inp["task"]
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ctx.server_url}/agents/{agent_name}",
            headers=ctx.headers,
            timeout=10,
        )
        if resp.status_code != 200:
            return f"Agent '{agent_name}' not found."
        agent_def = resp.json()

    delegate_job_data = {
        "job": {
            "agent_name": agent_name,
            "input": task,
            "conversation_id": ctx.job.get("conversation_id"),
        },
        "agent": {
            "name": agent_def["name"],
            "description": agent_def.get("description", ""),
            "prompt_template": agent_def.get("prompt_template", ""),
            "tools": list(agent_def.get("tools") or []),
            "knowledge_areas": list(
                agent_def.get("knowledge_areas") or []
            ),
        },
        "messages": [],
        "knowledge": [],
        "mcp_servers": [],
    }
    output, _tokens = await run_agent(
        delegate_job_data, ctx.settings, ctx.server_url,
        ctx.headers["x-worker-key"],
    )
    raw = f"[{agent_name}] {output}"
    return await process_tool_output(raw, ctx=ctx, tool_name="delegate_to_agent")


@builtin_tool(
    name="delegate_parallel",
    description=(
        "Delegate tasks to multiple agents in parallel. "
        "All agents run concurrently and results are returned together."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "delegations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "description": "Agent to delegate to",
                        },
                        "task": {
                            "type": "string",
                            "description": "Task description for this agent",
                        },
                    },
                    "required": ["agent_name", "task"],
                },
                "description": "List of {agent_name, task} to run in parallel",
            },
        },
        "required": ["delegations"],
    },
)
async def _handle_delegate_parallel(inp: dict, ctx: ToolContext) -> str:
    from crow.worker.executor import run_agent

    delegations = inp.get("delegations", [])
    if not delegations:
        return "No delegations provided."

    async def _run_one(d: dict) -> dict:
        name = d["agent_name"]
        task = d["task"]
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{ctx.server_url}/agents/{name}",
                headers=ctx.headers,
                timeout=10,
            )
            if resp.status_code != 200:
                return {
                    "agent": name,
                    "result": f"Agent '{name}' not found.",
                }
            agent_def = resp.json()

        delegate_job_data = {
            "job": {
                "agent_name": name,
                "input": task,
                "conversation_id": ctx.job.get("conversation_id"),
            },
            "agent": {
                "name": agent_def["name"],
                "description": agent_def.get("description", ""),
                "prompt_template": agent_def.get("prompt_template", ""),
                "tools": list(agent_def.get("tools") or []),
                "knowledge_areas": list(
                    agent_def.get("knowledge_areas") or []
                ),
                "max_iterations": agent_def.get("max_iterations"),
            },
            "messages": [],
            "knowledge": [],
            "mcp_servers": [],
        }
        output, _tokens = await run_agent(
            delegate_job_data, ctx.settings, ctx.server_url,
            ctx.headers["x-worker-key"],
        )
        return {"agent": name, "result": output}

    results = await asyncio.gather(*[_run_one(d) for d in delegations])
    raw = json.dumps(list(results), indent=2)
    return await process_tool_output(raw, ctx=ctx, tool_name="delegate_parallel")


@builtin_tool(
    name="spawn_job",
    description=(
        "Spawn a background job that runs immediately and independently. "
        "Returns instantly — the spawned job runs on a separate worker "
        "while you continue responding to the user. Use this to kick off "
        "long-running work (searching, research, analysis) while keeping "
        "the chat responsive."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "Agent to run (can be yourself or another agent)",
            },
            "task": {
                "type": "string",
                "description": (
                    "Detailed task description for the background job"
                ),
            },
        },
        "required": ["agent_name", "task"],
    },
)
async def _handle_spawn_job(inp: dict, ctx: ToolContext) -> str:
    payload = {
        "agent_name": inp["agent_name"],
        "input": inp["task"],
        "conversation_id": ctx.job.get("conversation_id"),
        "mode": "background",
        "user_id": ctx.job.get("user_id"),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ctx.server_url}/jobs",
            headers=ctx.headers,
            json=payload,
            timeout=10,
        )
        if resp.status_code >= 400:
            return f"Failed to spawn job: {resp.text}"
        data = resp.json()
        return (
            f"Background job spawned: {inp['agent_name']}"
            f" (job_id={data['job_id']}). It will run independently"
            f" and post updates to the conversation."
        )
