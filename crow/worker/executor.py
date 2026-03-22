"""Agent executor — runs a single agent job using the Anthropic API."""

import json
import logging
from pathlib import Path

import anthropic
import httpx
import jinja2

from crow.config.settings import Settings

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


def build_tool_definitions(tool_names: list[str]) -> list[dict]:
    """Build Anthropic tool definitions from tool names."""
    from crow.agents.tools import delegate, devbot, knowledge, pilot

    tool_map = {
        "delegate_to_agent": delegate.TOOL_DEF,
        "devbot.list_jobs": devbot.LIST_JOBS_DEF,
        "devbot.get_job": devbot.GET_JOB_DEF,
        "devbot.create_job": devbot.CREATE_JOB_DEF,
        "pilot.get_status": pilot.GET_STATUS_DEF,
        "knowledge.search": knowledge.SEARCH_DEF,
        "knowledge.write": knowledge.WRITE_DEF,
        "knowledge.archive": knowledge.ARCHIVE_DEF,
    }
    return [tool_map[name] for name in tool_names if name in tool_map]


async def execute_tool(
    tool_name: str,
    tool_input: dict,
    settings: Settings,
    server_url: str,
    worker_key: str,
    job: dict,
) -> str:
    """Execute a tool call and return the result as a string."""
    from crow.agents.tools import devbot, pilot

    if tool_name == "delegate_to_agent":
        # Delegation creates a new job on the server
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{server_url}/jobs/{job['id']}/result",
                headers={"x-worker-key": worker_key},
                json={
                    "output": f"Delegating to {tool_input['agent_name']}: {tool_input['task']}",
                    "tokens_used": 0,
                },
                timeout=10,
            )
        return f"Delegated to {tool_input['agent_name']}"

    elif tool_name == "devbot.list_jobs":
        return await devbot.list_jobs(
            settings.devbot_url,
            status=tool_input.get("status"),
            limit=tool_input.get("limit", 10),
        )

    elif tool_name == "devbot.get_job":
        return await devbot.get_job(settings.devbot_url, tool_input["job_id"])

    elif tool_name == "devbot.create_job":
        return await devbot.create_job(
            settings.devbot_url, tool_input["prompt"], tool_input["repo"]
        )

    elif tool_name == "pilot.get_status":
        return await pilot.get_status(settings.pilot_url)

    elif tool_name in ("knowledge.search", "knowledge.write", "knowledge.archive"):
        # Knowledge tools call back to the server
        async with httpx.AsyncClient() as client:
            if tool_name == "knowledge.search":
                resp = await client.get(
                    f"{server_url}/agents/{job['agent_name']}/knowledge",
                    params={"category": tool_input.get("category")},
                    timeout=10,
                )
                return resp.text
            elif tool_name == "knowledge.write":
                # TODO: implement write endpoint
                return json.dumps({"status": "knowledge write not yet implemented"})
            else:
                return json.dumps({"status": "knowledge archive not yet implemented"})

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


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

    if not agent:
        return f"Unknown agent: {job['agent_name']}", 0

    # Render system prompt
    prompt_context = {
        "devbot_url": settings.devbot_url,
        "pilot_url": settings.pilot_url,
    }

    # For PA agent, include available agents list
    if agent["name"] == "pa":
        # Minimal agent descriptions for the PA prompt
        prompt_context["agents"] = [
            {"name": "monitor", "description": "Watches devbot, pilot, erdo, trading systems"},
            {"name": "planner", "description": "Breaks down goals, coordinates work"},
            {"name": "reviewer", "description": "Reviews PRs and agent outputs"},
        ]

    system_prompt = render_prompt(agent["prompt_template"], prompt_context)

    # Build messages
    api_messages = []

    # Inject knowledge as tool_use/tool_result pairs (erdo pattern)
    if knowledge_entries:
        knowledge_summary = "\n\n".join(
            f"### [{e['category']}] {e['title']}\n{e['content']}"
            for e in knowledge_entries
        )
        api_messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "knowledge_context",
                    "content": knowledge_summary,
                }
            ],
        })

    # Add conversation history
    for msg in conversation_messages:
        api_messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })

    # If no conversation history, use the job input directly
    if not conversation_messages:
        api_messages.append({"role": "user", "content": job["input"]})

    # Build tool definitions
    tools = build_tool_definitions(agent.get("tools", []))

    # Call Claude
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    total_tokens = 0

    # Agentic loop
    max_iterations = 10
    for _ in range(max_iterations):
        kwargs = {
            "model": settings.anthropic_model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": api_messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = await client.messages.create(**kwargs)
        total_tokens += response.usage.input_tokens + response.usage.output_tokens

        # Check if we're done
        if response.stop_reason == "end_turn":
            # Extract text response
            text_parts = [
                block.text for block in response.content if block.type == "text"
            ]
            return "\n".join(text_parts) or "(no response)", total_tokens

        # Handle tool use
        if response.stop_reason == "tool_use":
            # Add assistant message with tool use
            api_messages.append({
                "role": "assistant",
                "content": [block.model_dump() for block in response.content],
            })

            # Execute each tool call
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await execute_tool(
                        block.name,
                        block.input,
                        settings,
                        server_url,
                        worker_key,
                        job,
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            api_messages.append({"role": "user", "content": tool_results})
        else:
            # Unexpected stop reason
            text_parts = [
                block.text for block in response.content if block.type == "text"
            ]
            return "\n".join(text_parts) or f"(stopped: {response.stop_reason})", total_tokens

    return "(max iterations reached)", total_tokens
