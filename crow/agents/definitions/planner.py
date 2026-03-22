from crow.agents.registry import AgentDef, ToolRef

planner = AgentDef(
    name="planner",
    description=(
        "Breaks down goals into tasks and coordinates work "
        "across systems (devbot, erdo, etc)."
    ),
    prompt_template="planner_system.md.j2",
    tools=[
        ToolRef("devbot.create_job"),
        ToolRef("devbot.list_jobs"),
        ToolRef("knowledge.search"),
        ToolRef("knowledge.write"),
    ],
    knowledge_areas=["planning", "goals", "coordination"],
)
