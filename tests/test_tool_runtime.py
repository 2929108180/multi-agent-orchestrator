from mao_cli.mcp_client import MCPCallOutput
from mao_cli.registry import MCPServerRecord, MCPToolRecord
from mao_cli.tool_runtime import ToolCall, execute_tool_call


class FakePool:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []

    def call_tool(self, server: MCPServerRecord, *, tool: str, arguments: dict | None) -> MCPCallOutput:
        self.calls.append((server.name, tool, arguments))
        return MCPCallOutput(text="ok")


def test_execute_tool_call_skips_confirmation_for_new_file_create() -> None:
    pool = FakePool()
    confirm_calls: list[tuple[str, str, str]] = []
    server = MCPServerRecord(
        name="mao_fs",
        transport="stdio",
        command="python",
        tools=[
            MCPToolRecord(
                name="mao_fs_write_text",
                description="write text",
                read_only_hint=False,
                destructive_hint=True,
            )
        ],
    )
    call = ToolCall(
        call_type="mcp",
        name="mao_fs.mao_fs_write_text",
        args={"path": "tmp/hello.txt", "content": "hello"},
        server="mao_fs",
        tool="mao_fs_write_text",
    )

    result = execute_tool_call(
        call,
        mcp_servers=[server],
        skills=[],
        pool=pool,
        confirm_callback=lambda tool_name, description, args_summary: confirm_calls.append((tool_name, description, args_summary)) or True,
    )

    assert result.ok is True
    assert pool.calls == [("mao_fs", "mao_fs_write_text", {"path": "tmp/hello.txt", "content": "hello"})]
    assert confirm_calls == []


def test_execute_tool_call_requires_confirmation_for_overwrite() -> None:
    pool = FakePool()
    confirm_calls: list[tuple[str, str, str]] = []
    server = MCPServerRecord(
        name="mao_fs",
        transport="stdio",
        command="python",
        tools=[
            MCPToolRecord(
                name="mao_fs_write_text",
                description="write text",
                read_only_hint=False,
                destructive_hint=True,
            )
        ],
    )
    call = ToolCall(
        call_type="mcp",
        name="mao_fs.mao_fs_write_text",
        args={"path": "tmp/hello.txt", "content": "hello", "overwrite": True},
        server="mao_fs",
        tool="mao_fs_write_text",
    )

    result = execute_tool_call(
        call,
        mcp_servers=[server],
        skills=[],
        pool=pool,
        confirm_callback=lambda tool_name, description, args_summary: confirm_calls.append((tool_name, description, args_summary)) or False,
    )

    assert result.ok is False
    assert result.output == "User denied this operation."
    assert pool.calls == []
    assert confirm_calls == [
        (
            "mao_fs_write_text",
            "overwrite file",
            '{"path": "tmp/hello.txt", "content": "hello", "overwrite": true}',
        )
    ]


def test_execute_tool_call_requires_confirmation_for_unknown_external_tool() -> None:
    pool = FakePool()
    confirm_calls: list[tuple[str, str, str]] = []
    server = MCPServerRecord(
        name="dameng_mcp",
        transport="stdio",
        command="python",
    )
    call = ToolCall(
        call_type="mcp",
        name="dameng_mcp.execute_sql",
        args={"sql": "DELETE FROM sys_user"},
        server="dameng_mcp",
        tool="execute_sql",
    )

    result = execute_tool_call(
        call,
        mcp_servers=[server],
        skills=[],
        pool=pool,
        confirm_callback=lambda tool_name, description, args_summary: confirm_calls.append((tool_name, description, args_summary)) or False,
    )

    assert result.ok is False
    assert result.output == "User denied this operation."
    assert pool.calls == []
    assert confirm_calls == [
        (
            "execute_sql",
            "external tool (dameng_mcp.execute_sql)",
            '{"sql": "DELETE FROM sys_user"}',
        )
    ]
