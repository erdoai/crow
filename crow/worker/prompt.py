"""Jinja2 prompt rendering."""

from pathlib import Path

import jinja2

PROMPTS_DIR = Path(__file__).parent.parent / "agents" / "prompts"


def render_prompt(template_name: str, context: dict) -> str:
    """Render a Jinja2 prompt template.

    If template_name is a .j2 filename, load from PROMPTS_DIR.
    Otherwise treat it as inline Jinja2 content (for imported agents).
    """
    if template_name.endswith(".j2") and (PROMPTS_DIR / template_name).exists():
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(PROMPTS_DIR)),
            undefined=jinja2.Undefined,
        )
        template = env.get_template(template_name)
    else:
        env = jinja2.Environment(undefined=jinja2.Undefined)
        template = env.from_string(template_name)
    return template.render(**context)
