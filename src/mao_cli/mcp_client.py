from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

import anyio

from mao_cli.registry import MCPServerRecord


class MCPToolInfo(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class MCPCallOutput:
    """Normalized output for `mao mcp call`."""

    text: str
    structured: Any | None = None


def _render_tool_content(result) -> str:
    """Best-effort rendering for CallToolResult.content."""
    parts: list[str] = []
    for item in getattr(result, "content", []) or []:
        item_type = getattr(item, "type", None)
        if item_type == "text":
            parts.append(getattr(item, "text", ""))
        else:
            # Fallback for non-text content.
            parts.append(f"[{item_type or 'content'}]")
    return "\n".join(part for part in parts if part)


async def call_mcp_tool(server: MCPServerRecord, *, tool: str, arguments: dict[str, Any] | None) -> MCPCallOutput:
    """Call one MCP tool using the server registry record.

    Note: FastMCP wraps tool inputs under a top-level `params` object.
    The CLI follows the MCP schema and expects callers to pass the wrapped shape.
    """

    from mcp.client.session import ClientSession

    if server.transport == "stdio":
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(command=server.command, args=server.args)
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments=arguments)
                text = _render_tool_content(result)
                structured = getattr(result, "structuredContent", None)
                return MCPCallOutput(text=text, structured=structured)

    if server.transport == "streamable-http":
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(server.url) as (read_stream, write_stream, _get_session_id):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments=arguments)
                text = _render_tool_content(result)
                structured = getattr(result, "structuredContent", None)
                return MCPCallOutput(text=text, structured=structured)

    raise ValueError(f"Unsupported MCP transport: {server.transport}")


async def list_mcp_tools(server: MCPServerRecord) -> list[MCPToolInfo]:
    """List tools exposed by the MCP server."""

    from mcp.client.session import ClientSession

    if server.transport == "stdio":
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(command=server.command, args=server.args)
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                return [
                    MCPToolInfo(
                        name=tool.name,
                        description=getattr(tool, "description", None),
                        input_schema=getattr(tool, "inputSchema", None),
                    )
                    for tool in result.tools
                ]

    if server.transport == "streamable-http":
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(server.url) as (read_stream, write_stream, _get_session_id):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                return [
                    MCPToolInfo(
                        name=tool.name,
                        description=getattr(tool, "description", None),
                        input_schema=getattr(tool, "inputSchema", None),
                    )
                    for tool in result.tools
                ]

    raise ValueError(f"Unsupported MCP transport: {server.transport}")


def list_mcp_tools_sync(server: MCPServerRecord) -> list[MCPToolInfo]:
    async def _runner() -> list[MCPToolInfo]:
        return await list_mcp_tools(server)

    return anyio.run(_runner)


def call_mcp_tool_sync(server: MCPServerRecord, *, tool: str, arguments: dict[str, Any] | None) -> MCPCallOutput:
    async def _runner() -> MCPCallOutput:
        return await call_mcp_tool(server, tool=tool, arguments=arguments)

    return anyio.run(_runner)


def parse_arguments_json(raw: str) -> dict[str, Any] | None:
    stripped = raw.strip()
    if not stripped:
        return None
    return json.loads(stripped)


def parse_arguments_file(path: Path) -> dict[str, Any] | None:
    return parse_arguments_json(path.read_text(encoding="utf-8"))
