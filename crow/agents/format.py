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
    if agent.get("mcp_configs"):
        frontmatter["mcp_servers"] = agent["mcp_configs"]  # inline map overrides list
    if agent.get("knowledge_areas"):
        frontmatter["knowledge_areas"] = list(agent["knowledge_areas"])
    if agent.get("parent_agent"):
        frontmatter["parent"] = agent["parent_agent"]
    if agent.get("max_iterations"):
        frontmatter["max_iterations"] = agent["max_iterations"]

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

    # mcp_servers can be a list of names OR a dict of inline configs
    mcp_servers_raw = frontmatter.get("mcp_servers", [])
    if isinstance(mcp_servers_raw, dict):
        mcp_servers = list(mcp_servers_raw.keys())  # names for the DB column
        mcp_configs = mcp_servers_raw               # full configs for mcp_configs column
    else:
        mcp_servers = mcp_servers_raw
        mcp_configs = None

    return {
        "name": frontmatter["name"],
        "description": frontmatter.get("description", ""),
        "prompt_template": prompt,
        "tools": frontmatter.get("tools", []),
        "mcp_servers": mcp_servers,
        "mcp_configs": mcp_configs,
        "knowledge_areas": frontmatter.get("knowledge_areas", []),
        "parent_agent": frontmatter.get("parent"),
        "max_iterations": frontmatter.get("max_iterations"),
    }
