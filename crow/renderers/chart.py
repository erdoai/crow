"""Built-in chart renderer — bar and line charts for terminal display.

Content part schema::

    {
        "type": "chart",
        "chart_type": "bar" | "line",
        "title": "Optional title",
        "data": [
            {"label": "Q1", "value": 45},
            {"label": "Q2", "value": 58}
        ]
    }
"""

from __future__ import annotations

from typing import Any

from rich.console import ConsoleRenderable
from rich.panel import Panel
from rich.text import Text

# Unicode blocks for sparkline rendering (8 levels)
_SPARK = " ▁▂▃▄▅▆▇█"
_BAR_CHAR = "█"
_BAR_HALF = "▌"
_BAR_WIDTH = 40


class ChartRenderer:
    """Renders ``chart`` content parts as Rich panels."""

    content_type = "chart"

    def render(self, data: dict[str, Any]) -> ConsoleRenderable:
        chart_type = data.get("chart_type", "bar")
        if chart_type == "line":
            return _render_line(data)
        return _render_bar(data)


def _render_bar(data: dict[str, Any]) -> ConsoleRenderable:
    items = data.get("data", [])
    if not items:
        return Panel("(no data)", title=data.get("title", "Chart"))

    max_val = max((d.get("value", 0) for d in items), default=1) or 1
    label_width = max((len(str(d.get("label", ""))) for d in items), default=1)

    lines = Text()
    for i, d in enumerate(items):
        label = str(d.get("label", ""))
        value = d.get("value", 0)
        bar_len = int((value / max_val) * _BAR_WIDTH)
        half = (value / max_val) * _BAR_WIDTH - bar_len >= 0.5

        bar = _BAR_CHAR * bar_len + (_BAR_HALF if half else "")

        lines.append(f"{label:>{label_width}}  ", style="bold")
        lines.append(bar, style="cyan")
        lines.append(f" {value}\n" if i < len(items) - 1 else f" {value}")

    return Panel(lines, title=data.get("title"), border_style="dim")


def _render_line(data: dict[str, Any]) -> ConsoleRenderable:
    items = data.get("data", [])
    if not items:
        return Panel("(no data)", title=data.get("title", "Chart"))

    values = [d.get("value", 0) for d in items]
    labels = [str(d.get("label", "")) for d in items]

    min_val = min(values)
    max_val = max(values)
    span = max_val - min_val or 1

    # Sparkline
    spark = ""
    for v in values:
        level = int(((v - min_val) / span) * (len(_SPARK) - 1))
        spark += _SPARK[level]

    lines = Text()
    lines.append(spark + "\n", style="cyan bold")

    # Labels row (spaced to match sparkline chars)
    if len(labels) <= 20:
        label_row = "  ".join(labels)
        lines.append(label_row, style="dim")
    else:
        # Too many labels — show first, middle, last
        lines.append(
            f"{labels[0]}{'':>{len(spark) - len(labels[0]) - len(labels[-1])}}{labels[-1]}",
            style="dim",
        )

    # Value range
    lines.append(f"\n{min_val} → {max_val}", style="dim italic")

    return Panel(lines, title=data.get("title"), border_style="dim")
