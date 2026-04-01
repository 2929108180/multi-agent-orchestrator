from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from mao_cli.core.models import WorkflowEvent
from mao_cli.mcp_client import MCPSessionPool, call_mcp_tool_sync
from mao_cli.registry import MCPServerRecord, SkillRecord, filter_mcp_servers_for, filter_skills_for


ToolCallType = Literal["mcp", "skill"]

_RISK_LABELS = {
    ("mao_fs", "mao_fs_write_text"): "overwrite file",
    ("mao_fs", "mao_fs_delete_file"): "delete file",
    ("mao_fs", "mao_fs_delete_dir"): "delete directory",
}

# Callback type: (tool_name, description, args_summary) -> bool (True=allow, False=deny)
ConfirmCallback = Any  # Actually: Callable[[str, str, str], bool] | None


def _find_tool_record(server_record: MCPServerRecord, tool_name: str):
    return next((tool for tool in server_record.tools if tool.name == tool_name), None)


def _risk_label(server_record: MCPServerRecord, tool_name: str) -> str:
    return _RISK_LABELS.get((server_record.name.lower(), tool_name), f"destructive tool ({server_record.name}.{tool_name})")


def _needs_confirmation(call: "ToolCall", server_record: MCPServerRecord) -> str | None:
    """Return a risk description if the call needs user confirmation."""
    tool_record = _find_tool_record(server_record, call.tool)

    # Conditional guardrails for tools whose risk depends on arguments.
    if server_record.name.lower() == "mao_fs" and call.tool == "mao_fs_write_text":
        overwrite = bool((call.args or {}).get("overwrite"))
        return _risk_label(server_record, call.tool) if overwrite else None

    if tool_record is not None:
        if tool_record.read_only_hint is True:
            return None
        if tool_record.destructive_hint is True:
            return _risk_label(server_record, call.tool)
        if tool_record.read_only_hint is False and tool_record.destructive_hint is False:
            return None

    # Unknown external tools default to confirmation.
    if server_record.name.lower() not in {"mao_mcp", "mao_fs"}:
        return f"external tool ({server_record.name}.{call.tool})"
    return None


@dataclass(frozen=True)
class ToolCall:
    call_type: ToolCallType
    name: str
    args: dict[str, Any] | None
    raw_args: str = ""
    server: str = ""
    tool: str = ""


@dataclass(frozen=True)
class ToolResult:
    call_type: ToolCallType
    name: str
    ok: bool
    output: str
    server: str = ""
    tool: str = ""


_TOOL_CALL_START = "TOOL_CALL:"
_TOOL_CALL_END = "END_TOOL_CALL"


def parse_tool_calls(text: str) -> list[ToolCall]:
    """Parse TOOL_CALL blocks from text.

    Protocol:

    TOOL_CALL:
    TYPE: mcp|skill
    NAME: <mcp_server>.<tool>   # TYPE=mcp
    NAME: <skill_name>          # TYPE=skill
    ARGS_JSON: <one-line json or empty>
    END_TOOL_CALL
    """

    lines = text.splitlines()
    calls: list[ToolCall] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() != _TOOL_CALL_START:
            index += 1
            continue

        index += 1
        block: list[str] = []
        while index < len(lines) and lines[index].strip() != _TOOL_CALL_END:
            block.append(lines[index])
            index += 1
        if index < len(lines) and lines[index].strip() == _TOOL_CALL_END:
            index += 1

        call = _parse_tool_call_block(block)
        if call is not None:
            calls.append(call)

    return calls


def _parse_tool_call_block(lines: list[str]) -> ToolCall | None:
    fields: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().upper()] = value.strip()

    raw_type = fields.get("TYPE", "").lower()
    if raw_type not in {"mcp", "skill"}:
        return None

    name = fields.get("NAME", "").strip()
    raw_args = fields.get("ARGS_JSON", "").strip()
    args = None
    if raw_args and raw_args.lower() not in {"null", "none"}:
        try:
            loaded = json.loads(raw_args)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            args = loaded

    server = ""
    tool = ""
    if raw_type == "mcp" and name:
        if "." in name:
            server, tool = name.split(".", 1)
        else:
            server = name

    return ToolCall(call_type=raw_type, name=name, args=args, raw_args=raw_args, server=server, tool=tool)


def render_tool_catalog(*, mcp_servers: list[MCPServerRecord], skills: list[SkillRecord]) -> str:
    lines: list[str] = [
        "Tool calling is enabled. You are an autonomous agent — use tools proactively to gather context.",
        "",
        "## Tool usage strategy",
        "- EXPLORE → UNDERSTAND → ACT. Never skip the first two steps.",
        "- Before modifying a file, ALWAYS read it first to understand context. Never edit blind.",
        "- When modifying code, think about dependencies: who calls this? what imports this?",
        "  If needed, read related files too before making changes.",
        "- When you need to use a tool, output ONLY one or more TOOL_CALL blocks (no extra text around them).",
        "- After tool results are provided, continue the user-facing answer normally.",
        "",
        "## Tool call format",
        "",
        "TOOL_CALL:",
        "TYPE: mcp|skill",
        "NAME: ...",
        "ARGS_JSON: <one-line json or empty>",
        "END_TOOL_CALL",
        "",
    ]

    if mcp_servers:
        lines.append("Available MCP tools (NAME uses <server>.<tool>):")
        for server in mcp_servers:
            if not server.enabled:
                continue
            if server.tools:
                for tool in server.tools:
                    if tool.enabled:
                        desc = f" - {tool.description}" if tool.description else ""
                        lines.append(f"- {server.name}.{tool.name}{desc}")
            else:
                lines.append(f"- {server.name}.* (tool list unknown; registry tools not imported)")
        lines.append("")

    bound = [skill for skill in skills if getattr(skill, "mcp_server", "") and getattr(skill, "mcp_tool", "")]
    if bound:
        lines.append("Available skills (TYPE=skill; mapped to MCP):")
        for skill in bound:
            lines.append(f"- {skill.name} -> {skill.mcp_server}.{skill.mcp_tool}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_tool_result(result: ToolResult, *, max_output_chars: int = 6000) -> str:
    output = result.output or ""
    if len(output) > max_output_chars:
        output = output[: max_output_chars - 3].rstrip() + "..."

    name = result.name
    lines = [
        "TOOL_RESULT:",
        f"TYPE: {result.call_type}",
        f"NAME: {name}",
        f"OK: {'yes' if result.ok else 'no'}",
        "OUTPUT:",
        output,
        "END_TOOL_RESULT",
    ]
    return "\n".join(lines)


def run_with_tools(
    *,
    gateway,
    role: str,
    base_prompt: str,
    project_root,
    runtime_root: str,
    config,
    event_handler=None,
    run_id: str = "",
    round_index: int = 0,
    max_tool_iters: int = 5,
    confirm_callback: ConfirmCallback = None,
) -> tuple[str, list[ToolResult]]:
    """Run `gateway.complete()` with an iterative tool execution loop."""

    model = config.providers[role].model
    mcp_servers = filter_mcp_servers_for(project_root, runtime_root, role=role, model=model)
    skills = filter_skills_for(project_root, runtime_root, role=role, model=model)

    tool_catalog = render_tool_catalog(mcp_servers=mcp_servers, skills=skills)
    prompt = base_prompt.rstrip() + "\n\n" + tool_catalog

    tool_trace: list[ToolResult] = []
    executed = 0

    with MCPSessionPool.open() as pool:
        while True:
            response = gateway.complete(role=role, prompt=prompt)
            calls = parse_tool_calls(response)
            if not calls:
                return response, tool_trace

            remaining = max_tool_iters - executed
            if remaining <= 0:
                prompt += "\n\n" + render_tool_result(
                    ToolResult(
                        call_type="mcp",
                        name="tool_loop",
                        ok=False,
                        output=f"Reached max_tool_iters={max_tool_iters}. Continue without further tool calls.",
                    )
                )
                final = gateway.complete(role=role, prompt=prompt)
                return final, tool_trace

            runnable = calls[:remaining]
            ignored = calls[remaining:]

            for call in runnable:
                executed += 1
                _emit_tool_event(
                    event_handler,
                    event_type="tool_call_started",
                    role=role,
                    model=model,
                    run_id=run_id,
                    round_index=round_index,
                    metadata={"type": call.call_type, "name": call.name},
                )
                result = execute_tool_call(
                    call,
                    mcp_servers=mcp_servers,
                    skills=skills,
                    pool=pool,
                    confirm_callback=confirm_callback,
                )
                tool_trace.append(result)
                _emit_tool_event(
                    event_handler,
                    event_type="tool_call_completed",
                    role=role,
                    model=model,
                    run_id=run_id,
                    round_index=round_index,
                    metadata={"type": result.call_type, "name": result.name, "ok": "yes" if result.ok else "no"},
                )
                prompt += "\n\n" + render_tool_result(result)

            if ignored:
                prompt += "\n\n" + render_tool_result(
                    ToolResult(
                        call_type="mcp",
                        name="tool_loop",
                        ok=False,
                        output=f"Ignored {len(ignored)} additional TOOL_CALL blocks because of max_tool_iters limit.",
                    )
                )


def _emit_tool_event(
    handler,
    *,
    event_type: str,
    role: str,
    model: str,
    run_id: str,
    round_index: int,
    metadata: dict[str, str],
) -> None:
    if handler is None:
        return
    handler(
        WorkflowEvent(
            event_type=event_type,
            role=role,
            model=model,
            run_id=run_id,
            round_index=round_index,
            metadata=metadata,
        )
    )


def execute_tool_call(
    call: ToolCall,
    *,
    mcp_servers: list[MCPServerRecord],
    skills: list[SkillRecord],
    pool: MCPSessionPool | None = None,
    confirm_callback: ConfirmCallback = None,
) -> ToolResult:
    if call.call_type == "skill":
        skill = next((item for item in skills if item.name.lower() == call.name.lower()), None)
        if skill is None:
            return ToolResult(call_type="skill", name=call.name, ok=False, output=f"Skill `{call.name}` not allowed or not found.")
        if not getattr(skill, "mcp_server", "") or not getattr(skill, "mcp_tool", ""):
            return ToolResult(
                call_type="skill",
                name=call.name,
                ok=False,
                output=f"Skill `{skill.name}` is not bound to an MCP tool. Bind it first.",
            )
        mapped = ToolCall(
            call_type="mcp",
            name=f"{skill.mcp_server}.{skill.mcp_tool}",
            args=call.args,
            raw_args=call.raw_args,
            server=skill.mcp_server,
            tool=skill.mcp_tool,
        )
        result = execute_tool_call(mapped, mcp_servers=mcp_servers, skills=skills, pool=pool, confirm_callback=confirm_callback)
        # Preserve the original skill name for the model.
        return ToolResult(call_type="skill", name=skill.name, ok=result.ok, output=result.output, server=result.server, tool=result.tool)

    if call.call_type != "mcp":
        return ToolResult(call_type=call.call_type, name=call.name, ok=False, output="Unsupported tool call type.")

    if not call.server or not call.tool:
        return ToolResult(
            call_type="mcp",
            name=call.name,
            ok=False,
            output="Invalid MCP tool name. Use NAME: <server>.<tool>.",
        )

    server_record = next((item for item in mcp_servers if item.name.lower() == call.server.lower()), None)
    if server_record is None:
        return ToolResult(
            call_type="mcp",
            name=call.name,
            ok=False,
            output=f"MCP server `{call.server}` not allowed or not found.",
            server=call.server,
            tool=call.tool,
        )

    if server_record.tools and not any(tool.name == call.tool and tool.enabled for tool in server_record.tools):
        return ToolResult(
            call_type="mcp",
            name=call.name,
            ok=False,
            output=f"Tool `{call.tool}` not found or disabled on MCP server `{server_record.name}`.",
            server=server_record.name,
            tool=call.tool,
        )

    # User confirmation for destructive / unknown external tools.
    if confirm_callback is not None:
        risk_desc = _needs_confirmation(call, server_record)
        if risk_desc is not None:
            args_summary = json.dumps(call.args or {}, ensure_ascii=False)
            if len(args_summary) > 200:
                args_summary = args_summary[:200] + "..."
            allowed = confirm_callback(call.tool, risk_desc, args_summary)
            if not allowed:
                return ToolResult(
                    call_type="mcp",
                    name=call.name,
                    ok=False,
                    output="User denied this operation.",
                    server=server_record.name,
                    tool=call.tool,
                )

    # MCP servers use different argument conventions:
    # - FastMCP (Pydantic): expects {"params": {field: value, ...}}
    # - Raw MCP SDK: expects flat {field: value, ...}
    # - Model may output either shape, or None/empty.
    #
    # Strategy: try the original arguments first. If the server returns a
    # validation error mentioning "params", retry with a {"params": ...} wrapper
    # (and vice-versa). This makes us compatible with both FastMCP and raw SDK
    # servers without hardcoding per-server knowledge.
    original_args = call.args if call.args is not None else {}

    def _try_call(arguments):
        if pool is not None:
            return pool.call_tool(server_record, tool=call.tool, arguments=arguments)
        return call_mcp_tool_sync(server_record, tool=call.tool, arguments=arguments)

    def _is_params_error(text: str) -> bool:
        lowered = text.lower()
        return "params" in lowered and ("field required" in lowered or "validation error" in lowered)

    try:
        output = _try_call(original_args)
        # FastMCP returns validation errors as successful text responses, not exceptions.
        if output.text and _is_params_error(output.text):
            raise ValueError(output.text)
    except (Exception,) as first_err:
        # Retry with alternate wrapping.
        alt_args = original_args
        if isinstance(original_args, dict) and "params" not in original_args:
            alt_args = {"params": original_args}
        elif isinstance(original_args, dict) and "params" in original_args:
            alt_args = original_args.get("params", {})
            if not isinstance(alt_args, dict):
                alt_args = {}
        else:
            alt_args = {"params": {}}

        if alt_args == original_args:
            # No alternate shape to try.
            return ToolResult(
                call_type="mcp",
                name=call.name,
                ok=False,
                output=f"Tool call failed: {first_err}",
                server=server_record.name,
                tool=call.tool,
            )

        try:
            output = _try_call(alt_args)
            if output.text and _is_params_error(output.text):
                return ToolResult(
                    call_type="mcp",
                    name=call.name,
                    ok=False,
                    output=f"Tool call failed after retry: {output.text[:300]}",
                    server=server_record.name,
                    tool=call.tool,
                )
        except Exception as retry_err:  # noqa: BLE001
            return ToolResult(
                call_type="mcp",
                name=call.name,
                ok=False,
                output=f"Tool call failed: {first_err} (retry also failed: {retry_err})",
                server=server_record.name,
                tool=call.tool,
            )

    rendered = output.text
    if not rendered and output.structured is not None:
        rendered = json.dumps(output.structured, ensure_ascii=False, indent=2)

    if not server_record.tools:
        rendered = "(registry tool list unknown)\n" + (rendered or "(no content)")

    return ToolResult(
        call_type="mcp",
        name=call.name,
        ok=True,
        output=rendered or "(no content)",
        server=server_record.name,
        tool=call.tool,
    )
