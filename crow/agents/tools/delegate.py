"""Tool for PA agent to delegate work to specialist agents."""

from crow.agents.tools import tool_def

TOOL_DEF = tool_def(
    name="delegate_to_agent",
    description="Delegate a task to a specialist agent. It will handle the task.",
    parameters={
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "Name of the agent to delegate to (monitor, planner, reviewer)",
            },
            "task": {
                "type": "string",
                "description": "Clear description of what the agent should do",
            },
        },
        "required": ["agent_name", "task"],
    },
)


async def execute(db, agent_name: str, task: str, conversation_id: str | None = None) -> str:
    """Create a job for the target agent. Returns job ID."""
    job_id = await db.create_job(
        agent_name=agent_name,
        input_text=task,
        conversation_id=conversation_id,
    )
    return f"Delegated to {agent_name}. Job ID: {job_id}"
