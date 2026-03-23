"""Agent executor — runs a single agent job using the Anthropic API."""

import json
import logging
from pathlib import Path

import anthropic
import httpx
import jinja2

from crow.config.settings import Settings
from crow.worker.mcp_client import MCPConnection, connect_mcp

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "agents" / "prompts"


def render_prompt(template_name: str, context: dict) -> str:
    """Render a Jinja2 prompt template."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(PROMPTS_DIR)),
        undefined=jinja2.Undefined,
    )
    template = env.get_template(template_name)
    return template.render(**context)


# -- Built-in tools (delegate, knowledge) --

BUILTIN_TOOLS = {
    "delegate_to_agent": {
        "name": "delegate_to_agent",
        "description": "Delegate a task to a specialist agent.",
        "input_schema": {
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
    },
    "knowledge_search": {
        "name": "knowledge_search",
        "description": "Search PARA knowledge base via semantic + keyword.",
        "input_schema": {
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
    },
    "knowledge_write": {
        "name": "knowledge_write",
        "description": "Save a learning to PARA knowledge base.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["project", "area", "resource"],
                },
                "title": {"type": "string"},
                "content": {"type": "string"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["category", "title", "content"],
        },
    },
    "knowledge_archive": {
        "name": "knowledge_archive",
        "description": "Archive a knowledge entry.",
        "input_schema": {
            "type": "object",
            "properties": {
                "knowledge_id": {"type": "string"},
            },
            "required": ["knowledge_id"],
        },
    },
    "create_agent": {
        "name": "create_agent",
        "description": (
            "Create or update an agent. Use when the user asks"
            " to set up a new agent or modify an existing one."
        ),
        "input_schema": {
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
                        " create_agent, list_agents, delete_agent"
                    ),
                },
            },
            "required": ["name", "description", "prompt_template"],
        },
    },
    "list_agents": {
        "name": "list_agents",
        "description": "List all configured agents with their descriptions and tools.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    "delete_agent": {
        "name": "delete_agent",
        "description": "Delete an agent by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Agent name to delete"},
            },
            "required": ["name"],
        },
    },
}


async def execute_builtin(
    tool_name: str,
    tool_input: dict,
    server_url: str,
    worker_key: str,
    job: dict,
) -> str:
    """Execute a built-in tool."""
    headers = {"x-worker-key": worker_key}

    if tool_name == "delegate_to_agent":
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{server_url}/messages",
                json={
                    "text": tool_input["task"],
                    "thread_id": (
                        f"delegate-{job.get('conversation_id', 'none')}"
                    ),
                },
                timeout=10,
            )
        return f"Delegated to {tool_input['agent_name']}: job created."

    elif tool_name == "knowledge_search":
        async with httpx.AsyncClient() as client:
            params = {
                k: v
                for k, v in {
                    "category": tool_input.get("category")
                }.items()
                if v
            }
            resp = await client.get(
                f"{server_url}/agents/{job['agent_name']}/knowledge",
                params=params,
                timeout=10,
            )
            return resp.text

    elif tool_name == "knowledge_write":
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{server_url}/agents/{job['agent_name']}/knowledge",
                headers=headers,
                json={
                    "category": tool_input["category"],
                    "title": tool_input["title"],
                    "content": tool_input["content"],
                    "tags": tool_input.get("tags", []),
                },
                timeout=10,
            )
            return resp.text

    elif tool_name == "knowledge_archive":
        async with httpx.AsyncClient() as client:
            kid = tool_input["knowledge_id"]
            resp = await client.post(
                f"{server_url}/agents/{job['agent_name']}"
                f"/knowledge/{kid}/archive",
                headers=headers,
                timeout=10,
            )
            return resp.text

    elif tool_name == "create_agent":
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{server_url}/agents",
                json={
                    "name": tool_input["name"],
                    "description": tool_input["description"],
                    "prompt_template": tool_input.get("prompt_template", ""),
                    "tools": tool_input.get("tools", []),
                    "mcp_servers": tool_input.get("mcp_servers", []),
                    "knowledge_areas": tool_input.get("knowledge_areas", []),
                },
                timeout=10,
            )
            return resp.text

    elif tool_name == "list_agents":
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{server_url}/agents",
                timeout=10,
            )
            return resp.text

    elif tool_name == "delete_agent":
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{server_url}/agents/{tool_input['name']}",
                timeout=10,
            )
            return resp.text

    return json.dumps({"error": f"Unknown built-in: {tool_name}"})


async def run_agent(
    job_data: dict,
    settings: Settings,
    server_url: str,
    worker_key: str,
) -> tuple[str, int]:
    """Run an agent job. Returns (output, tokens_used)."""
    job = job_data["job"]
    agent = job_data["agent"]
    conversation_messages = job_data.get("messages", [])
    knowledge_entries = job_data.get("knowledge", [])
    mcp_configs = job_data.get("mcp_servers", [])

    if not agent:
        return f"Unknown agent: {job['agent_name']}", 0

    # Render system prompt
    prompt_context = {
        "devbot_url": settings.devbot_url,
        "pilot_url": settings.pilot_url,
    }
    if agent["name"] == "pa":
        prompt_context["agents"] = [
            {
                "name": "monitor",
                "description": "Watches devbot, pilot, erdo, trading",
            },
            {
                "name": "planner",
                "description": "Breaks down goals, coordinates work",
            },
            {
                "name": "reviewer",
                "description": "Reviews PRs and agent outputs",
            },
        ]

    system_prompt = render_prompt(agent["prompt_template"], prompt_context)

    # Inject knowledge into system prompt
    if knowledge_entries:
        knowledge_section = "\n\n## Your knowledge\n\n"
        knowledge_section += "\n\n".join(
            f"### [{e['category']}] {e['title']}\n{e['content']}"
            for e in knowledge_entries
        )
        system_prompt += knowledge_section

    # Build messages
    api_messages = []
    for msg in conversation_messages:
        api_messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })
    if not conversation_messages:
        api_messages.append({"role": "user", "content": job["input"]})

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
        max_iterations = 10

        for _ in range(max_iterations):
            kwargs: dict = {
                "model": settings.anthropic_model,
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": api_messages,
            }
            if tools:
                kwargs["tools"] = tools

            response = await client.messages.create(**kwargs)
            total_tokens += (
                response.usage.input_tokens + response.usage.output_tokens
            )

            if response.stop_reason == "end_turn":
                text_parts = [
                    b.text for b in response.content if b.type == "text"
                ]
                return (
                    "\n".join(text_parts) or "(no response)",
                    total_tokens,
                )

            if response.stop_reason == "tool_use":
                api_messages.append({
                    "role": "assistant",
                    "content": [
                        b.model_dump() for b in response.content
                    ],
                })

                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    # Dispatch: built-in or MCP?
                    if block.name in BUILTIN_TOOLS:
                        result = await execute_builtin(
                            block.name,
                            block.input,
                            server_url,
                            worker_key,
                            job,
                        )
                    else:
                        # Try MCP connections
                        result = None
                        for conn in mcp_connections:
                            if conn.has_tool(block.name):
                                result = await conn.call_tool(
                                    block.name, block.input
                                )
                                break
                        if result is None:
                            result = json.dumps(
                                {"error": f"Unknown tool: {block.name}"}
                            )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

                api_messages.append(
                    {"role": "user", "content": tool_results}
                )
            else:
                text_parts = [
                    b.text for b in response.content if b.type == "text"
                ]
                return (
                    "\n".join(text_parts)
                    or f"(stopped: {response.stop_reason})"
                ), total_tokens

        return "(max iterations reached)", total_tokens

    finally:
        if mcp_stack:
            await mcp_stack.__aexit__(None, None, None)
