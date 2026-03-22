from dataclasses import dataclass, field


@dataclass
class ToolRef:
    name: str


@dataclass
class AgentDef:
    name: str
    description: str
    prompt_template: str
    tools: list[ToolRef] = field(default_factory=list)
    knowledge_areas: list[str] = field(default_factory=list)


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, AgentDef] = {}

    def register(self, agent: AgentDef) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> AgentDef | None:
        return self._agents.get(name)

    def list(self) -> list[AgentDef]:
        return list(self._agents.values())
