"""Agent executor — runs a single agent job using the Anthropic API."""

import asyncio
import base64
import json
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
import httpx
import jinja2

from crow.config.settings import Settings
from crow.worker.mcp_client import MCPConnection, connect_mcp

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "agents" / "prompts"


def render_prompt(template_name: str, context: dict) -> str:
    """Render a Jinja2 prompt template.

    If template_name is a .j2 filename, load from PROMPTS_DIR.
    Otherwise treat it as inline Jinja2 content (for imported agents).
    """
    if template_name.endswith(".j2") and (PROMPTS_DIR / template_name).exists():
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(PROMPTS_DIR)),
            undefined=jinja2.Undefined,
        )
        template = env.get_template(template_name)
    else:
        env = jinja2.Environment(undefined=jinja2.Undefined)
        template = env.from_string(template_name)
    return template.render(**context)


# -- Built-in tool registry --

# Populated by @builtin_tool decorator
BUILTIN_TOOLS: dict[str, dict] = {}
TOOL_HANDLERS: dict[
    str, Callable[..., Coroutine[Any, Any, str]]
] = {}


@dataclass
class ToolContext:
    server_url: str
    headers: dict
    job: dict
    settings: Settings | None


def builtin_tool(
    *, name: str, description: str, input_schema: dict
) -> Callable:
    """Register a built-in tool — binds schema + handler in one place."""
    def decorator(
        fn: Callable[..., Coroutine[Any, Any, str]],
    ) -> Callable[..., Coroutine[Any, Any, str]]:
        BUILTIN_TOOLS[name] = {
            "name": name,
            "description": description,
            "input_schema": input_schema,
        }
        TOOL_HANDLERS[name] = fn
        return fn
    return decorator


# -- Tool handlers --


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
    return f"[{agent_name}] {output}"


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
    return json.dumps(list(results), indent=2)


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
    name="execute_code",
    description=(
        "Execute Python code in a sandboxed environment (E2B). "
        "Use for data analysis, web scraping, file processing, "
        "API calls, or any computation. Packages can be installed "
        "with pip inside the code (e.g. subprocess or !pip install)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute",
            },
            "packages": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Pip packages to install before running"
                    " (e.g. ['requests', 'beautifulsoup4'])"
                ),
            },
        },
        "required": ["code"],
    },
)
async def _handle_execute_code(inp: dict, ctx: ToolContext) -> str:
    try:
        from e2b_code_interpreter import AsyncSandbox
    except ImportError:
        return (
            "e2b-code-interpreter package not installed."
            " Run: pip install e2b-code-interpreter"
        )

    code = inp["code"]
    packages = inp.get("packages") or []

    try:
        sandbox = await AsyncSandbox.create(timeout=120)
        try:
            if packages:
                pip_cmd = f"pip install {' '.join(packages)}"
                await sandbox.commands.run(pip_cmd, timeout=60)

            execution = await sandbox.run_code(code, timeout=90)

            parts = []
            if execution.logs.stdout:
                parts.append(
                    "stdout:\n" + "\n".join(execution.logs.stdout)
                )
            if execution.logs.stderr:
                parts.append(
                    "stderr:\n" + "\n".join(execution.logs.stderr)
                )
            if execution.error:
                parts.append(
                    f"error: {execution.error.name}:"
                    f" {execution.error.value}"
                )
            if execution.results:
                for r in execution.results:
                    if hasattr(r, "text") and r.text:
                        parts.append(f"result: {r.text}")

            return "\n".join(parts) if parts else "(no output)"
        finally:
            await sandbox.kill()
    except Exception as e:
        return f"Code execution failed: {e}"


@builtin_tool(
    name="create_attachment",
    description=(
        "Create a file attachment on your response. Use to send"
        " documents like cover letters, reports, or data files."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": (
                    "Filename with extension"
                    " (e.g. 'cover_letter.md', 'report.csv')"
                ),
            },
            "content": {
                "type": "string",
                "description": "The text content of the file",
            },
            "content_type": {
                "type": "string",
                "description": "MIME type (default: text/plain)",
            },
        },
        "required": ["filename", "content"],
    },
)
async def _handle_create_attachment(inp: dict, ctx: ToolContext) -> str:
    content = inp["content"]
    content_b64 = base64.b64encode(
        content.encode("utf-8")
    ).decode("ascii")
    ct = inp.get("content_type", "text/plain")
    filename = inp["filename"]
    size_bytes = len(content.encode("utf-8"))
    job_id = ctx.job.get("id", "unknown")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ctx.server_url}/jobs/{job_id}/attachments",
            headers=ctx.headers,
            json={
                "filename": filename,
                "content_type": ct,
                "data": content_b64,
                "size_bytes": size_bytes,
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            return f"Failed to create attachment: {resp.text}"
        att_data = resp.json()
        return f"Created attachment: {filename} (id={att_data['id']})"


@builtin_tool(
    name="evaluate_run",
    description=(
        "Evaluate a completed agent run using LLM-as-judge. "
        "Returns a structured evaluation with score (1-5), summary, "
        "strengths, weaknesses, and improvement suggestions. "
        "Use this to assess agent performance before making "
        "improvements."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "ID of the completed job to evaluate",
            },
            "criteria": {
                "type": "string",
                "description": (
                    "Optional evaluation criteria or rubric. "
                    "If omitted, uses general quality assessment."
                ),
            },
        },
        "required": ["job_id"],
    },
)
async def _handle_evaluate_run(inp: dict, ctx: ToolContext) -> str:
    eval_job_id = inp["job_id"]
    criteria = inp.get("criteria", "")

    # Fetch job + conversation messages
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ctx.server_url}/jobs/{eval_job_id}/evaluation-data",
            headers=ctx.headers,
            timeout=30,
        )
        if resp.status_code != 200:
            return json.dumps(
                {"error": f"Job {eval_job_id} not found"}
            )
        eval_data = resp.json()

    eval_job = eval_data["job"]
    eval_messages = eval_data["messages"]

    if eval_job.get("status") != "completed":
        return json.dumps({
            "error": (
                f"Job status is '{eval_job.get('status')}',"
                " not 'completed'"
            )
        })

    # Build conversation transcript
    conversation_text = "\n".join(
        f"[{m['role']}] {m['content']}" for m in eval_messages
    )

    eval_system = (
        "You are an expert evaluator of AI agent runs. "
        "Analyze the agent's performance and return ONLY valid JSON:\n"
        "{\n"
        '  "score": <integer 1-5, 1=poor 3=adequate 5=excellent>,\n'
        '  "summary": "<one paragraph assessment>",\n'
        '  "strengths": ["<strength>", ...],\n'
        '  "weaknesses": ["<weakness>", ...],\n'
        '  "suggestions": ["<actionable improvement>", ...]\n'
        "}"
    )

    criteria_section = (
        f"\n\nEvaluation criteria: {criteria}" if criteria else ""
    )

    eval_user_msg = (
        f"Evaluate this agent run:\n\n"
        f"Agent: {eval_job.get('agent_name', 'unknown')}\n"
        f"Task input: {eval_job.get('input', '')}\n"
        f"Final output: {eval_job.get('output', '')}\n"
        f"Tokens used: {eval_job.get('tokens_used', 'unknown')}\n\n"
        f"Conversation ({len(eval_messages)} messages):\n"
        f"{conversation_text}"
        f"{criteria_section}"
    )

    # Call Claude as judge
    if not ctx.settings or not ctx.settings.anthropic_api_key:
        return json.dumps(
            {"error": "No Anthropic API key configured"}
        )

    ai_client = anthropic.AsyncAnthropic(
        api_key=ctx.settings.anthropic_api_key,
    )
    response = await ai_client.messages.create(
        model=ctx.settings.anthropic_model,
        max_tokens=1024,
        system=eval_system,
        messages=[{"role": "user", "content": eval_user_msg}],
    )

    result_text = response.content[0].text
    try:
        evaluation = json.loads(result_text)
    except json.JSONDecodeError:
        evaluation = {"raw": result_text, "parse_error": True}

    evaluation["job_id"] = eval_job_id
    evaluation["agent_name"] = eval_job.get("agent_name")
    evaluation["tokens_used_by_evaluation"] = (
        response.usage.input_tokens + response.usage.output_tokens
    )

    return json.dumps(evaluation, indent=2)


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

    ctx = ToolContext(
        server_url=server_url,
        headers={"x-worker-key": worker_key},
        job=job,
        settings=settings,
    )
    return await handler(tool_input, ctx)


# -- Agent runner --


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
        knowledge_section = "\n\n## Your knowledge\n\n"
        knowledge_section += "\n\n".join(
            f"### [{e['category']}] {e['title']}\n{e['content']}"
            for e in knowledge_entries
        )
        system_prompt += knowledge_section

    # Build messages (with attachment content blocks)
    api_messages = []
    for msg in conversation_messages:
        attachments = msg.get("attachments") or []
        if attachments:
            content_blocks = []
            if msg["content"]:
                content_blocks.append(
                    {"type": "text", "text": msg["content"]}
                )
            for att in attachments:
                ct = att["content_type"]
                if ct.startswith("image/"):
                    content_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": ct,
                            "data": att["data"],
                        },
                    })
                elif ct == "application/pdf":
                    content_blocks.append({
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": att["data"],
                        },
                    })
                else:
                    content_blocks.append({
                        "type": "text",
                        "text": (
                            f"[Attached file: {att['filename']}"
                            f" ({ct}, {att['size_bytes']} bytes)]"
                        ),
                    })
            api_messages.append(
                {"role": msg["role"], "content": content_blocks}
            )
        else:
            api_messages.append(
                {"role": msg["role"], "content": msg["content"]}
            )
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
        max_iterations = agent.get("max_iterations") or 10

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
                output_text = "\n".join(text_parts) or "(no response)"

                # Stream the final text response as chunks
                if job.get("conversation_id"):
                    chunk_headers = {"x-worker-key": worker_key}
                    chunk_url = f"{server_url}/jobs/{job.get('id')}/chunk"
                    async with httpx.AsyncClient() as hc:
                        # Send in ~100 char chunks for smooth streaming
                        pos = 0
                        while pos < len(output_text):
                            chunk = output_text[pos:pos + 100]
                            await hc.post(
                                chunk_url,
                                headers=chunk_headers,
                                json={
                                    "text": chunk,
                                    "agent_name": job.get("agent_name"),
                                },
                                timeout=5,
                            )
                            pos += 100
                            await asyncio.sleep(0.03)

                return output_text, total_tokens

            if response.stop_reason == "tool_use":
                api_messages.append({
                    "role": "assistant",
                    "content": [
                        b.model_dump() for b in response.content
                    ],
                })

                tool_blocks = [
                    b for b in response.content if b.type == "tool_use"
                ]

                async def _exec_tool(block):
                    if block.name in BUILTIN_TOOLS:
                        result = await execute_builtin(
                            block.name,
                            block.input,
                            server_url,
                            worker_key,
                            job,
                            settings=settings,
                        )
                    else:
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
                    return {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }

                tool_results = await asyncio.gather(
                    *[_exec_tool(b) for b in tool_blocks]
                )

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
