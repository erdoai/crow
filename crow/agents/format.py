"""Agent markdown format — serialize/deserialize agent definitions."""

import re
from pathlib import Path

import yaml

PROMPTS_DIR = Path(__file__).parent / "prompts"


def resolve_prompt_content(prompt_template: str) -> str:
    """Read prompt template file content, or return as-is if inline."""
    if prompt_template.endswith(".j2"):
        path = PROMPTS_DIR / prompt_template
        if path.exists():
            return path.read_text()
    return prompt_template


def agent_to_markdown(agent: dict) -> str:
    """Serialize an agent definition to markdown with YAML frontmatter."""
    prompt_content = resolve_prompt_content(agent["prompt_template"])
    frontmatter = {
        "name": agent["name"],
        "description": agent["description"],
    }
    if agent.get("tools"):
        frontmatter["tools"] = list(agent["tools"])
    if agent.get("mcp_servers"):
        frontmatter["mcp_servers"] = list(agent["mcp_servers"])
    if agent.get("knowledge_areas"):
        frontmatter["knowledge_areas"] = list(agent["knowledge_areas"])

    fm_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).strip()
    return f"---\n{fm_str}\n---\n\n{prompt_content}"


def markdown_to_agent(content: str) -> dict:
    """Parse a markdown agent file (YAML frontmatter + prompt body)."""
    match = re.match(r"^---\s*\n(.+?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not match:
        raise ValueError("Invalid agent file: missing YAML frontmatter (---)")

    frontmatter = yaml.safe_load(match.group(1))
    prompt = match.group(2).strip()

    if not frontmatter or "name" not in frontmatter:
        raise ValueError("Invalid agent file: frontmatter must include 'name'")

    return {
        "name": frontmatter["name"],
        "description": frontmatter.get("description", ""),
        "prompt_template": prompt,
        "tools": frontmatter.get("tools", []),
        "mcp_servers": frontmatter.get("mcp_servers", []),
        "knowledge_areas": frontmatter.get("knowledge_areas", []),
    }
