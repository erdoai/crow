"""Built-in tool registry for crow worker."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from crow.config.settings import Settings

# Populated by @builtin_tool decorator
BUILTIN_TOOLS: dict[str, dict] = {}
TOOL_HANDLERS: dict[
    str, Callable[..., Coroutine[Any, Any, str]]
] = {}


@dataclass
class ToolContext:
    server_url: str
    headers: dict
    job: dict
    settings: Settings | None


def builtin_tool(
    *, name: str, description: str, input_schema: dict
) -> Callable:
    """Register a built-in tool — binds schema + handler in one place."""
    def decorator(
        fn: Callable[..., Coroutine[Any, Any, str]],
    ) -> Callable[..., Coroutine[Any, Any, str]]:
        BUILTIN_TOOLS[name] = {
            "name": name,
            "description": description,
            "input_schema": input_schema,
        }
        TOOL_HANDLERS[name] = fn
        return fn
    return decorator


# Import all tool modules to trigger decorator registration
from crow.worker.tools import (  # noqa: E402, F401
    agents,
    code,
    delegation,
    evaluation,
    files,
    knowledge,
    profile,
    scheduling,
    store,
    web,
)
