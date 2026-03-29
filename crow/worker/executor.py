"""Agent executor — runs a single agent job via LLM with tool support."""

import asyncio
import json
import logging
from collections.abc import Callable

import httpx

from crow.config.settings import Settings
from crow.llm.client import StreamEvent, call_llm_with_fallback
from crow.worker.context import build_api_messages, inject_store_state
from crow.worker.mcp_client import MCPConnection, connect_mcp
from crow.worker.prompt import render_prompt
from crow.worker.tools import BUILTIN_TOOLS, TOOL_HANDLERS, ToolContext

logger = logging.getLogger(__name__)

SHUTDOWN_SENTINEL = "(shutdown)"


async def _is_job_cancelled(
    server_url: str, worker_key: str, job_id: str | None
) -> bool:
    """Check if a job has been cancelled (status=failed)."""
    if not job_id:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{server_url}/jobs/{job_id}",
                headers={"x-worker-key": worker_key},
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json().get("status") == "failed"
    except Exception:
        pass
    return False


async def _send_heartbeat(
    server_url: str, worker_key: str, job_id: str
) -> None:
    """Tell the server this job is still alive — resets the reaper clock."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{server_url}/jobs/{job_id}/heartbeat",
                headers={"x-worker-key": worker_key},
                timeout=5,
            )
    except Exception:
        logger.warning("Failed to send heartbeat for job %s", job_id)


async def _save_turn(
    server_url: str,
    worker_key: str,
    job_id: str,
    role: str,
    content: list[dict],
) -> None:
    """Save an intermediate conversation turn to the DB via the server."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{server_url}/jobs/{job_id}/turn",
                headers={"x-worker-key": worker_key},
                json={
                    "role": role,
                    "content": content,
                },
                timeout=10,
            )
    except Exception:
        logger.warning("Failed to save turn for job %s", job_id)


# -- Dispatcher --


async def execute_builtin(
    tool_name: str,
    tool_input: dict,
    server_url: str,
    worker_key: str,
    job: dict,
    settings: "Settings | None" = None,
) -> str:
    """Execute a built-in tool."""
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown built-in: {tool_name}"})

    tool_headers = {"x-worker-key": worker_key}
    if job.get("_job_token"):
        tool_headers["x-job-token"] = job["_job_token"]
    ctx = ToolContext(
        server_url=server_url,
        headers=tool_headers,
        job=job,
        settings=settings,
    )
    try:
        return await handler(tool_input, ctx)
    except Exception as e:
        logger.exception("Built-in tool %s failed", tool_name)
        return json.dumps({"error": f"Tool {tool_name} failed: {e}"})


# -- Agent runner --


async def run_agent(
    job_data: dict,
    settings: Settings,
    server_url: str,
    worker_key: str,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[str, int]:
    """Run an agent job. Returns (output, tokens_used)."""
    job = job_data["job"]
    job["_job_token"] = job_data.get("job_token")
    agent = job_data["agent"]
    conversation_messages = job_data.get("messages", [])
    knowledge_entries = job_data.get("knowledge", [])
    mcp_configs = job_data.get("mcp_servers", [])

    if not agent:
        return f"Unknown agent: {job['agent_name']}", 0

    # Render system prompt
    sub_agents = job_data.get("sub_agents", [])
    prompt_context = {
        "devbot_url": settings.devbot_url,
        "pilot_url": settings.pilot_url,
        "sub_agents": sub_agents,
        # backwards compat with PA template that uses
        # {% for agent in agents %}
        "agents": sub_agents,
    }

    system_prompt = render_prompt(agent["prompt_template"], prompt_context)

    # Inject knowledge into system prompt
    if knowledge_entries:
        parts = []
        for e in knowledge_entries:
            header = f"### [{e['category']}] {e['title']}"
            if e.get("source_ref"):
                header += f"\nSource: {e['source_ref']}"
            if e.get("updated_at"):
                header += f"\nUpdated: {e['updated_at']}"
            parts.append(f"{header}\n{e['content']}")
        system_prompt += "\n\n## Your knowledge\n\n" + "\n\n".join(parts)

    # Build messages (with attachment content blocks)
    # Background jobs use their task input, not conversation history
    job_mode = job.get("mode", "chat")
    if job_mode == "background":
        conversation_messages = []

    api_messages = build_api_messages(conversation_messages, job["input"])

    # Inject agent store state before the last user message.
    # Placed here (not in system prompt) to preserve prompt caching.
    await inject_store_state(
        api_messages,
        agent.get("tools", []),
        server_url,
        worker_key,
        agent["name"],
    )

    # Collect built-in tool definitions
    builtin_names = set(agent.get("tools", []))
    tools = [
        BUILTIN_TOOLS[name]
        for name in builtin_names
        if name in BUILTIN_TOOLS
    ]

    # Connect to MCP servers and collect their tools
    mcp_connections: list[MCPConnection] = []
    mcp_stack = None

    try:
        if mcp_configs:
            from contextlib import AsyncExitStack

            mcp_stack = AsyncExitStack()
            await mcp_stack.__aenter__()

            for cfg in mcp_configs:
                try:
                    conn = await mcp_stack.enter_async_context(
                        connect_mcp(cfg)
                    )
                    mcp_tools = await conn.list_tools()
                    tools.extend(mcp_tools)
                    mcp_connections.append(conn)
                    logger.info(
                        "MCP %s: %d tools",
                        cfg["name"],
                        len(mcp_tools),
                    )
                except Exception:
                    logger.exception(
                        "Failed to connect MCP server: %s", cfg["name"]
                    )

        # LLM call loop with streaming and fallback
        total_tokens = 0
        max_iterations = agent.get("max_iterations") or 10
        content_parts: list[dict] = []

        chunk_headers = {"x-worker-key": worker_key}
        chunk_url = f"{server_url}/jobs/{job.get('id')}/chunk"
        stream_chunks = job.get("conversation_id") is not None
        job_id = job.get("id")

        for _ in range(max_iterations):
            # Check for graceful shutdown
            if should_stop and should_stop():
                logger.info("Shutdown requested, requeueing job %s", job_id)
                return SHUTDOWN_SENTINEL, total_tokens

            # Check if job was cancelled before each LLM call
            if await _is_job_cancelled(server_url, worker_key, job_id):
                return "(cancelled)", total_tokens

            # Stream text chunks to the frontend
            async def on_stream_event(event: StreamEvent):
                if event.type == "text_delta" and event.text and stream_chunks:
                    async with httpx.AsyncClient() as hc:
                        await hc.post(
                            chunk_url,
                            headers=chunk_headers,
                            json={
                                "text": event.text,
                                "agent_name": job.get("agent_name"),
                            },
                            timeout=5,
                        )

            response = await call_llm_with_fallback(
                settings,
                system=system_prompt,
                messages=api_messages,
                tools=tools or None,
                on_event=on_stream_event,
            )

            collected_content = response.content
            stop_reason = response.stop_reason
            total_tokens += response.usage_input + response.usage_output

            # Reset reaper clock after each LLM call
            await _send_heartbeat(server_url, worker_key, job_id)

            if stop_reason == "end_turn":
                for b in collected_content:
                    if b["type"] == "text" and b["text"].strip():
                        content_parts.append({"type": "text", "text": b["text"]})
                return content_parts if content_parts else "(no response)", total_tokens

            if stop_reason == "tool_use":
                api_messages.append({
                    "role": "assistant",
                    "content": collected_content,
                })

                # Persist the assistant tool_use turn
                await _save_turn(
                    server_url, worker_key, job_id,
                    "assistant", collected_content,
                )

                tool_blocks = [
                    b for b in collected_content if b["type"] == "tool_use"
                ]

                # Stream tool_call chunks before execution
                if stream_chunks:
                    async with httpx.AsyncClient() as hc:
                        for tb in tool_blocks:
                            await hc.post(
                                chunk_url,
                                headers=chunk_headers,
                                json={
                                    "type": "tool_call",
                                    "tool_name": tb["name"],
                                    "agent_name": job.get("agent_name"),
                                },
                                timeout=5,
                            )

                async def _exec_tool(block):
                    tool_name = block["name"]
                    tool_input = block["input"]
                    if tool_name in BUILTIN_TOOLS:
                        result = await execute_builtin(
                            tool_name,
                            tool_input,
                            server_url,
                            worker_key,
                            job,
                            settings=settings,
                        )
                    else:
                        result = None
                        for conn in mcp_connections:
                            if conn.has_tool(tool_name):
                                result = await conn.call_tool(
                                    tool_name, tool_input
                                )
                                break
                        if result is None:
                            result = json.dumps(
                                {"error": f"Unknown tool: {tool_name}"}
                            )
                    return {
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": result,
                    }

                tool_results = await asyncio.gather(
                    *[_exec_tool(b) for b in tool_blocks]
                )

                # Tell the server we're still alive after tool execution
                await _send_heartbeat(server_url, worker_key, job_id)

                # Add all parts chronologically: text, tool calls, tool results
                for b in collected_content:
                    if b["type"] == "text" and b["text"].strip():
                        content_parts.append({"type": "text", "text": b["text"]})

                for tb, tr in zip(tool_blocks, tool_results):
                    content_parts.append({
                        "type": "tool_call",
                        "name": tb["name"],
                        "input": tb["input"],
                    })
                    content_parts.append({
                        "type": "tool_result",
                        "name": tb["name"],
                        "result": tr["content"] or "",
                    })

                    # Stream tool result to frontend
                    if stream_chunks:
                        async with httpx.AsyncClient() as hc:
                            await hc.post(
                                chunk_url,
                                headers=chunk_headers,
                                json={
                                    "type": "tool_result",
                                    "tool_name": tb["name"],
                                    "text": tr["content"] or "",
                                    "agent_name": job.get("agent_name"),
                                },
                                timeout=5,
                            )

                api_messages.append(
                    {"role": "user", "content": tool_results}
                )

                # Persist the tool_result turn
                await _save_turn(
                    server_url, worker_key, job_id,
                    "user", list(tool_results),
                )
            else:
                text_parts = [
                    b["text"] for b in collected_content if b["type"] == "text"
                ]
                return (
                    "\n".join(text_parts)
                    or f"(stopped: {stop_reason})"
                ), total_tokens

        return "(max iterations reached)", total_tokens

    finally:
        if mcp_stack:
            await mcp_stack.__aexit__(None, None, None)
