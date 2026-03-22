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

    headers = {"x-worker-key": worker_key}
    # Normalize: Claude returns underscore names, our refs use dots
    prefixes = ("devbot_", "pilot_", "knowledge_")
    if tool_name.startswith(prefixes):
        tool_name = tool_name.replace("_", ".", 1)

    if tool_name == "delegate_to_agent":
        # Create a child job for the target agent on the server
        agent_name = tool_input["agent_name"]
        task = tool_input["task"]
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{server_url}/messages",
                json={
                    "text": task,
                    "thread_id": (
                        f"delegate-{job.get('conversation_id', 'none')}"
                    ),
                },
                timeout=10,
            )
            resp.raise_for_status()
        return f"Delegated to {agent_name}: job created. It will run asynchronously."

    elif tool_name == "devbot.list_jobs":
        return await devbot.list_jobs(
            settings.devbot_url,
            status=tool_input.get("status"),
            limit=tool_input.get("limit", 10),
        )

    elif tool_name == "devbot.get_job":
        return await devbot.get_job(
            settings.devbot_url, tool_input["job_id"]
        )

    elif tool_name == "devbot.create_job":
        return await devbot.create_job(
            settings.devbot_url,
            tool_input["prompt"],
            tool_input["repo"],
        )

    elif tool_name == "pilot.get_status":
        return await pilot.get_status(settings.pilot_url)

    elif tool_name == "knowledge.search":
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{server_url}/agents/{job['agent_name']}/knowledge",
                params={
                    k: v
                    for k, v in {"category": tool_input.get("category")}.items()
                    if v
                },
                timeout=10,
            )
            return resp.text

    elif tool_name == "knowledge.write":
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

    elif tool_name == "knowledge.archive":
        async with httpx.AsyncClient() as client:
            kid = tool_input["knowledge_id"]
            resp = await client.post(
                f"{server_url}/agents/{job['agent_name']}/knowledge/{kid}/archive",
                headers=headers,
                timeout=10,
            )
            return resp.text

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
        prompt_context["agents"] = [
            {
                "name": "monitor",
                "description": "Watches devbot, pilot, erdo, trading systems",
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

    # Inject knowledge into system prompt (simpler and more reliable
    # than tool_use/tool_result pairs which need careful ordering)
    if knowledge_entries:
        knowledge_section = "\n\n## Your knowledge\n\n"
        knowledge_section += "\n\n".join(
            f"### [{e['category']}] {e['title']}\n{e['content']}"
            for e in knowledge_entries
        )
        system_prompt += knowledge_section

    # Build messages from conversation history
    api_messages = []
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

        # Check if we're done
        if response.stop_reason == "end_turn":
            text_parts = [
                block.text
                for block in response.content
                if block.type == "text"
            ]
            return "\n".join(text_parts) or "(no response)", total_tokens

        # Handle tool use
        if response.stop_reason == "tool_use":
            api_messages.append({
                "role": "assistant",
                "content": [
                    block.model_dump() for block in response.content
                ],
            })

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
            text_parts = [
                block.text
                for block in response.content
                if block.type == "text"
            ]
            return (
                "\n".join(text_parts)
                or f"(stopped: {response.stop_reason})"
            ), total_tokens

    return "(max iterations reached)", total_tokens
