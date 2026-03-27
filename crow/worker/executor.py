"""Agent executor — runs a single agent job using the Anthropic API."""

import asyncio
import json
import logging

import anthropic
import httpx

from crow.config.settings import Settings
from crow.worker.context import build_api_messages, inject_store_state
from crow.worker.mcp_client import MCPConnection, connect_mcp
from crow.worker.prompt import render_prompt
from crow.worker.tools import BUILTIN_TOOLS, TOOL_HANDLERS, ToolContext

logger = logging.getLogger(__name__)


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

        # Call Claude
        client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key
        )
        total_tokens = 0
        max_iterations = agent.get("max_iterations") or 10
        content_parts: list[dict] = []  # chronological content parts

        for _ in range(max_iterations):
            kwargs: dict = {
                "model": settings.anthropic_model,
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": api_messages,
            }
            if tools:
                kwargs["tools"] = tools

            # Use streaming for the Claude API call
            chunk_headers = {"x-worker-key": worker_key}
            chunk_url = f"{server_url}/jobs/{job.get('id')}/chunk"
            stream_chunks = job.get("conversation_id") is not None

            collected_content = []
            stop_reason = None
            usage_input = 0
            usage_output = 0

            async with client.messages.stream(**kwargs) as stream:
                async with httpx.AsyncClient() as hc:
                    async for event in stream:
                        if event.type == "content_block_start":
                            if event.content_block.type == "text":
                                collected_content.append({
                                    "type": "text",
                                    "text": "",
                                })
                            elif event.content_block.type == "tool_use":
                                collected_content.append({
                                    "type": "tool_use",
                                    "id": event.content_block.id,
                                    "name": event.content_block.name,
                                    "input": "",
                                })
                        elif event.type == "content_block_delta":
                            if event.delta.type == "text_delta":
                                collected_content[-1]["text"] += event.delta.text
                                if stream_chunks:
                                    await hc.post(
                                        chunk_url,
                                        headers=chunk_headers,
                                        json={
                                            "text": event.delta.text,
                                            "agent_name": job.get("agent_name"),
                                        },
                                        timeout=5,
                                    )
                            elif event.delta.type == "input_json_delta":
                                collected_content[-1]["input"] += event.delta.partial_json
                        elif event.type == "message_delta":
                            stop_reason = event.delta.stop_reason
                            usage_output += event.usage.output_tokens
                        elif event.type == "message_start":
                            usage_input += event.message.usage.input_tokens

            total_tokens += usage_input + usage_output

            # Parse tool_use inputs from accumulated JSON strings
            for block in collected_content:
                if block["type"] == "tool_use" and isinstance(block["input"], str):
                    try:
                        block["input"] = json.loads(block["input"]) if block["input"] else {}
                    except json.JSONDecodeError:
                        block["input"] = {}

            if stop_reason == "end_turn":
                for b in collected_content:
                    if b["type"] == "text" and b["text"].strip():
                        content_parts.append({"type": "text", "text": b["text"]})
                return json.dumps(content_parts) if content_parts else "(no response)", total_tokens

            if stop_reason == "tool_use":
                api_messages.append({
                    "role": "assistant",
                    "content": collected_content,
                })

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
