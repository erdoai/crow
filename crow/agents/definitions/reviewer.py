from crow.agents.registry import AgentDef, ToolRef

reviewer = AgentDef(
    name="reviewer",
    description=(
        "Reviews outputs from agent runs — PRs, code changes, "
        "job results — for quality and correctness."
    ),
    prompt_template="reviewer_system.md.j2",
    tools=[
        ToolRef("devbot.get_job"),
        ToolRef("devbot.list_jobs"),
        ToolRef("knowledge.search"),
        ToolRef("knowledge.write"),
    ],
    knowledge_areas=["review-standards", "quality"],
)
