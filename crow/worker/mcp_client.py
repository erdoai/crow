"""MCP client — connects to MCP servers, lists tools, calls tools."""

import logging
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logger = logging.getLogger(__name__)


def _mcp_tool_to_anthropic(tool: Any) -> dict:
    """Convert an MCP tool definition to Anthropic API format."""
    name = tool.name.replace(".", "_").replace("-", "_")
    return {
        "name": name,
        "description": tool.description or "",
        "input_schema": (
            tool.inputSchema
            if tool.inputSchema
            else {"type": "object", "properties": {}}
        ),
    }


@asynccontextmanager
async def connect_mcp(server_config: dict):
    """Connect to an MCP server. Yields an MCPConnection."""
    transport = server_config.get("transport", "stdio")

    if transport == "stdio":
        command = server_config["command"]
        parts = command.split()
        params = StdioServerParameters(
            command=parts[0],
            args=parts[1:] if len(parts) > 1 else [],
            env=server_config.get("env"),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield MCPConnection(session, server_config["name"])

    elif transport == "http":
        from mcp.client.streamable_http import streamablehttp_client

        url = server_config["url"]
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield MCPConnection(session, server_config["name"])
    else:
        raise ValueError(f"Unknown transport: {transport}")


class MCPConnection:
    """Wrapper around an MCP session for tool discovery and calling."""

    def __init__(self, session: ClientSession, server_name: str):
        self.session = session
        self.server_name = server_name
        self._tools: list[dict] | None = None
        self._tool_names: set[str] | None = None

    async def list_tools(self) -> list[dict]:
        """List tools in Anthropic API format."""
        if self._tools is None:
            result = await self.session.list_tools()
            self._tools = [_mcp_tool_to_anthropic(t) for t in result.tools]
            self._tool_names = {t["name"] for t in self._tools}
        return self._tools

    def has_tool(self, name: str) -> bool:
        """Check if this server provides a tool by name."""
        return name in (self._tool_names or set())

    async def call_tool(self, name: str, arguments: dict) -> str:
        """Call a tool and return the result as a string."""
        result = await self.session.call_tool(name, arguments)
        # MCP returns a list of content blocks
        parts = []
        for block in result.content:
            if hasattr(block, "text"):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts) if parts else "(empty result)"
