"""Agent tools — each module exposes tool definitions usable by the Anthropic API."""

from typing import Any


def tool_def(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """Helper to build an Anthropic tool definition."""
    return {
        "name": name.replace(".", "_"),
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": parameters.get("properties", {}),
            "required": parameters.get("required", []),
        },
    }
