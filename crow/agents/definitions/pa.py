from crow.agents.registry import AgentDef, ToolRef

pa = AgentDef(
    name="pa",
    description=(
        "Personal Assistant — routes all inbound messages "
        "to the right specialist agent or handles directly."
    ),
    prompt_template="pa_system.md.j2",
    tools=[
        ToolRef("delegate_to_agent"),
        ToolRef("knowledge.search"),
    ],
    knowledge_areas=["routing", "user-preferences"],
)
