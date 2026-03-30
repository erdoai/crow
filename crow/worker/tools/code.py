"""Code execution tool: execute_code."""

import os

from crow.worker.tools import ToolContext, builtin_tool
from crow.worker.tools.output import process_tool_output


def _collect_sandbox_envs() -> dict[str, str]:
    """Collect API keys and credentials to forward to the E2B sandbox."""
    envs = {}
    for key, value in os.environ.items():
        if not value:
            continue
        if key == "E2B_API_KEY":
            continue
        if key.startswith("CROW_") and ("API_KEY" in key or "API_ID" in key):
            envs[key.removeprefix("CROW_")] = value
        elif "API_KEY" in key or "APP_ID" in key or "API_ID" in key:
            envs[key] = value
    return envs


@builtin_tool(
    name="execute_code",
    description=(
        "Execute Python code in a sandboxed environment (E2B). "
        "Use for data analysis, web scraping, file processing, "
        "API calls, or any computation. Packages can be installed "
        "with pip inside the code (e.g. subprocess or !pip install)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute",
            },
            "packages": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Pip packages to install before running"
                    " (e.g. ['requests', 'beautifulsoup4'])"
                ),
            },
        },
        "required": ["code"],
    },
)
async def _handle_execute_code(inp: dict, ctx: ToolContext) -> str:
    try:
        from e2b_code_interpreter import AsyncSandbox
    except ImportError:
        return (
            "e2b-code-interpreter package not installed."
            " Run: pip install e2b-code-interpreter"
        )

    code = inp["code"]
    packages = inp.get("packages") or []

    # Forward API keys to the sandbox so code can call external APIs
    sandbox_envs = _collect_sandbox_envs()

    try:
        sandbox = await AsyncSandbox.create(timeout=120, envs=sandbox_envs)
        try:
            if packages:
                pip_cmd = f"pip install {' '.join(packages)}"
                await sandbox.commands.run(pip_cmd, timeout=60)

            execution = await sandbox.run_code(code, timeout=90)

            parts = []
            if execution.logs.stdout:
                parts.append(
                    "stdout:\n" + "\n".join(execution.logs.stdout)
                )
            if execution.logs.stderr:
                parts.append(
                    "stderr:\n" + "\n".join(execution.logs.stderr)
                )
            if execution.error:
                parts.append(
                    f"error: {execution.error.name}:"
                    f" {execution.error.value}"
                )
            if execution.results:
                for r in execution.results:
                    if hasattr(r, "text") and r.text:
                        parts.append(f"result: {r.text}")

            raw = "\n".join(parts) if parts else "(no output)"
            return await process_tool_output(
                raw, ctx=ctx, tool_name="execute_code",
            )
        finally:
            await sandbox.kill()
    except Exception as e:
        return f"Code execution failed: {e}"
