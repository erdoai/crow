"""Pluggable content-part renderer registry.

Agents can emit custom content types in their message content (JSONB array).
Renderers transform these into Rich renderables for terminal display.

External packages register custom renderers without modifying core code::

    from crow.renderers import register_renderer

    class MyRenderer:
        content_type = "my-widget"

        def render(self, data: dict) -> str:
            return f"Widget: {data['value']}"

    register_renderer(MyRenderer())

Built-in renderers (chart) are auto-registered on import.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from rich.console import ConsoleRenderable
from rich.text import Text


@runtime_checkable
class ContentRenderer(Protocol):
    """Protocol for content-part renderers.

    Attributes:
        content_type: The ``type`` value this renderer handles (e.g. ``"chart"``).
    """

    content_type: str

    def render(self, data: dict[str, Any]) -> str | ConsoleRenderable:
        """Return a Rich renderable or plain string for terminal output."""
        ...


_registry: dict[str, ContentRenderer] = {}


def register_renderer(renderer: ContentRenderer) -> None:
    """Register a renderer for a content-part type."""
    _registry[renderer.content_type] = renderer


def get_renderer(content_type: str) -> ContentRenderer | None:
    """Look up a renderer by content type. Returns ``None`` if not found."""
    return _registry.get(content_type)


def render_part(part: dict[str, Any]) -> str | ConsoleRenderable:
    """Render a single content part, falling back to text/JSON for unknown types."""
    renderer = get_renderer(part.get("type", ""))
    if renderer:
        return renderer.render(part)
    if "text" in part:
        return Text(str(part["text"]))
    return Text(json.dumps(part, indent=2), style="dim")


def render_message_content(
    parts: list[dict[str, Any]],
) -> list[str | ConsoleRenderable]:
    """Render all content parts of a message."""
    return [render_part(p) for p in parts]


# Auto-register built-in renderers
from crow.renderers.chart import ChartRenderer  # noqa: E402

register_renderer(ChartRenderer())
