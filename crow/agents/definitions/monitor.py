from crow.agents.registry import AgentDef, ToolRef

monitor = AgentDef(
    name="monitor",
    description=(
        "Watches devbot jobs, pilot status, erdo agent runs, "
        "and trading systems. Surfaces problems and status."
    ),
    prompt_template="monitor_system.md.j2",
    tools=[
        ToolRef("devbot.list_jobs"),
        ToolRef("devbot.get_job"),
        ToolRef("pilot.get_status"),
        ToolRef("knowledge.search"),
        ToolRef("knowledge.write"),
    ],
    knowledge_areas=["monitoring", "incidents", "system-health"],
)
