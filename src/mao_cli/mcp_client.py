from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any

from pydantic import BaseModel

import anyio

from mao_cli.registry import MCPServerRecord


class MCPToolInfo(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    read_only_hint: bool | None = None
    destructive_hint: bool | None = None
    idempotent_hint: bool | None = None
    open_world_hint: bool | None = None


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


def _tool_info_from_mcp(tool: Any) -> MCPToolInfo:
    annotations = getattr(tool, "annotations", None)
    return MCPToolInfo(
        name=tool.name,
        description=getattr(tool, "description", None),
        input_schema=getattr(tool, "inputSchema", None),
        read_only_hint=getattr(annotations, "readOnlyHint", None),
        destructive_hint=getattr(annotations, "destructiveHint", None),
        idempotent_hint=getattr(annotations, "idempotentHint", None),
        open_world_hint=getattr(annotations, "openWorldHint", None),
    )


def _stdio_transport_cm(server: MCPServerRecord):
    from mcp.client.stdio import StdioServerParameters, stdio_client

    env = server.env or None
    params = StdioServerParameters(command=server.command, args=server.args, env=env)
    return stdio_client(params)


def _streamable_http_transport_cm(server: MCPServerRecord):
    from mcp.client.streamable_http import streamablehttp_client

    return streamablehttp_client(server.url)


def _client_session_cm(read_stream: Any, write_stream: Any):
    from mcp.client.session import ClientSession

    return ClientSession(read_stream, write_stream)


# ---------------------------------------------------------------------------
# Single-shot helpers (open + close per call — used by CLI commands)
# ---------------------------------------------------------------------------

async def call_mcp_tool(server: MCPServerRecord, *, tool: str, arguments: dict[str, Any] | None) -> MCPCallOutput:
    """Call one MCP tool using the server registry record."""

    if server.transport == "stdio":
        async with _stdio_transport_cm(server) as (read_stream, write_stream):
            async with _client_session_cm(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments=arguments)
                text = _render_tool_content(result)
                structured = getattr(result, "structuredContent", None)
                return MCPCallOutput(text=text, structured=structured)

    if server.transport == "streamable-http":
        async with _streamable_http_transport_cm(server) as (read_stream, write_stream, _get_session_id):
            async with _client_session_cm(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments=arguments)
                text = _render_tool_content(result)
                structured = getattr(result, "structuredContent", None)
                return MCPCallOutput(text=text, structured=structured)

    raise ValueError(f"Unsupported MCP transport: {server.transport}")


async def list_mcp_tools(server: MCPServerRecord) -> list[MCPToolInfo]:
    """List tools exposed by the MCP server."""

    if server.transport == "stdio":
        async with _stdio_transport_cm(server) as (read_stream, write_stream):
            async with _client_session_cm(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                return [_tool_info_from_mcp(tool) for tool in result.tools]

    if server.transport == "streamable-http":
        async with _streamable_http_transport_cm(server) as (read_stream, write_stream, _get_session_id):
            async with _client_session_cm(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                return [_tool_info_from_mcp(tool) for tool in result.tools]

    raise ValueError(f"Unsupported MCP transport: {server.transport}")


def list_mcp_tools_sync(server: MCPServerRecord) -> list[MCPToolInfo]:
    async def _runner() -> list[MCPToolInfo]:
        return await list_mcp_tools(server)

    return anyio.run(_runner)


def call_mcp_tool_sync(server: MCPServerRecord, *, tool: str, arguments: dict[str, Any] | None) -> MCPCallOutput:
    async def _runner() -> MCPCallOutput:
        return await call_mcp_tool(server, tool=tool, arguments=arguments)

    return anyio.run(_runner)


# ---------------------------------------------------------------------------
# Pooled session — keeps server processes alive across multiple tool calls
# ---------------------------------------------------------------------------

class MCPSessionPool:
    """Holds persistent MCP client sessions keyed by server name.

    Usage (synchronous, used by run_with_tools):

        with MCPSessionPool.open() as pool:
            output = pool.call_tool(server_record, tool="x", arguments={...})
            output2 = pool.call_tool(server_record, tool="y", arguments={...})
        # All server processes are torn down here.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}  # server_name -> ClientSession
        self._cleanup_stack: list[Any] = []  # context managers to close
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    async def _get_session(self, server: MCPServerRecord):
        key = server.name.lower()
        if key in self._sessions:
            return self._sessions[key]

        if server.transport == "stdio":
            cm = _stdio_transport_cm(server)
            read_stream, write_stream = await cm.__aenter__()
            self._cleanup_stack.append(cm)
        elif server.transport == "streamable-http":
            cm = _streamable_http_transport_cm(server)
            read_stream, write_stream, _ = await cm.__aenter__()
            self._cleanup_stack.append(cm)
        else:
            raise ValueError(f"Unsupported MCP transport: {server.transport}")

        session_cm = _client_session_cm(read_stream, write_stream)
        session = await session_cm.__aenter__()
        self._cleanup_stack.append(session_cm)
        await session.initialize()
        self._sessions[key] = session
        return session

    async def _call_tool(self, server: MCPServerRecord, *, tool: str, arguments: dict[str, Any] | None) -> MCPCallOutput:
        session = await self._get_session(server)
        result = await session.call_tool(tool, arguments=arguments)
        text = _render_tool_content(result)
        structured = getattr(result, "structuredContent", None)
        return MCPCallOutput(text=text, structured=structured)

    async def _close(self) -> None:
        for cm in reversed(self._cleanup_stack):
            try:
                await cm.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
        self._sessions.clear()
        self._cleanup_stack.clear()

    # --- Synchronous API ---

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None:
            return self._loop

        loop = asyncio.new_event_loop()
        ready = threading.Event()

        def _runner() -> None:
            asyncio.set_event_loop(loop)
            ready.set()
            loop.run_forever()
            loop.close()

        thread = threading.Thread(target=_runner, name="mao-mcp-session-pool", daemon=True)
        thread.start()
        ready.wait()
        self._loop = loop
        self._thread = thread
        return loop

    def _run_coro(self, coro):
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()

    def call_tool(self, server: MCPServerRecord, *, tool: str, arguments: dict[str, Any] | None) -> MCPCallOutput:
        return self._run_coro(self._call_tool(server, tool=tool, arguments=arguments))

    def close(self) -> None:
        loop = self._loop
        thread = self._thread
        if loop is None or thread is None:
            return
        try:
            self._run_coro(self._close())
        except Exception:  # noqa: BLE001
            pass
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        self._loop = None
        self._thread = None

    @staticmethod
    @contextmanager
    def open():
        pool = MCPSessionPool()
        try:
            yield pool
        finally:
            pool.close()


def parse_arguments_json(raw: str) -> dict[str, Any] | None:
    stripped = raw.strip()
    if not stripped:
        return None
    return json.loads(stripped)


def parse_arguments_file(path: Path) -> dict[str, Any] | None:
    return parse_arguments_json(path.read_text(encoding="utf-8"))
