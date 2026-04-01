from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from mao_cli.skills import SkillEntry, discover_skills


class SkillRecord(BaseModel):
    name: str
    description: str
    path: str
    source: str = "local"
    enabled: bool = True
    roles: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    # Optional mapping to an MCP tool (Skill -> MCP indirection).
    mcp_server: str = ""
    mcp_tool: str = ""


class MCPToolRecord(BaseModel):
    name: str
    description: str
    enabled: bool = True
    roles: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    read_only_hint: bool | None = None
    destructive_hint: bool | None = None
    idempotent_hint: bool | None = None
    open_world_hint: bool | None = None


class MCPServerRecord(BaseModel):
    name: str
    transport: str
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str = ""
    # Environment variables for stdio servers (best-effort; may be omitted).
    env: dict[str, str] = Field(default_factory=dict)
    source: str = "local"
    enabled: bool = True
    roles: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    tools: list[MCPToolRecord] = Field(default_factory=list)


def registry_root(project_root: Path, runtime_root: str) -> Path:
    root = project_root / runtime_root / "registry"
    root.mkdir(parents=True, exist_ok=True)
    return root


def skills_registry_path(project_root: Path, runtime_root: str) -> Path:
    return registry_root(project_root, runtime_root) / "skills.json"


def mcp_registry_path(project_root: Path, runtime_root: str) -> Path:
    return registry_root(project_root, runtime_root) / "mcp_servers.json"


def load_skill_registry(project_root: Path, runtime_root: str) -> list[SkillRecord]:
    path = skills_registry_path(project_root, runtime_root)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [SkillRecord.model_validate(item) for item in payload]


def save_skill_registry(project_root: Path, runtime_root: str, records: list[SkillRecord]) -> Path:
    path = skills_registry_path(project_root, runtime_root)
    path.write_text(
        json.dumps([record.model_dump() for record in records], indent=2),
        encoding="utf-8",
    )
    return path


def import_local_skills(project_root: Path, runtime_root: str) -> Path:
    discovered = discover_skills(project_root)
    records = [
        SkillRecord(
            name=entry.name,
            description=entry.description,
            path=entry.path,
            source="local-import",
        )
        for entry in discovered
    ]
    return save_skill_registry(project_root, runtime_root, records)


def registered_or_discovered_skills(project_root: Path, runtime_root: str) -> list[SkillRecord]:
    registered = load_skill_registry(project_root, runtime_root)
    if registered:
        return [record for record in registered if record.enabled]
    return [
        SkillRecord(
            name=entry.name,
            description=entry.description,
            path=entry.path,
            source="discovered",
        )
        for entry in discover_skills(project_root)
    ]


def filter_skills_for(
    project_root: Path,
    runtime_root: str,
    *,
    role: str,
    model: str,
) -> list[SkillRecord]:
    records = registered_or_discovered_skills(project_root, runtime_root)
    visible: list[SkillRecord] = []
    bypass_grants = role == "architect"
    for record in records:
        if not record.enabled:
            continue
        if bypass_grants:
            visible.append(record)
            continue
        role_match = not record.roles or role in record.roles
        model_match = not record.models or model in record.models
        if role_match and model_match:
            visible.append(record)
    return visible


def load_mcp_registry(project_root: Path, runtime_root: str) -> list[MCPServerRecord]:
    path = mcp_registry_path(project_root, runtime_root)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [MCPServerRecord.model_validate(item) for item in payload]


def filter_mcp_servers_for(
    project_root: Path,
    runtime_root: str,
    *,
    role: str,
    model: str,
) -> list[MCPServerRecord]:
    records = load_mcp_registry(project_root, runtime_root)
    visible: list[MCPServerRecord] = []
    bypass_grants = role == "architect"
    for record in records:
        if not record.enabled:
            continue
        if bypass_grants:
            visible.append(record)
            continue
        role_match = not record.roles or role in record.roles
        model_match = not record.models or model in record.models
        if role_match and model_match:
            visible.append(record)
    return visible


def save_mcp_registry(project_root: Path, runtime_root: str, records: list[MCPServerRecord]) -> Path:
    path = mcp_registry_path(project_root, runtime_root)
    path.write_text(
        json.dumps([record.model_dump() for record in records], indent=2),
        encoding="utf-8",
    )
    return path


def _default_claude_desktop_config_paths() -> list[Path]:
    """Best-effort locations for Claude Desktop config.

    We intentionally keep this conservative: project manifest + Claude Desktop only.
    """

    paths: list[Path] = []

    system = platform.system().lower()
    if system == "windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            paths.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
    elif system == "darwin":
        paths.append(Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json")
    else:
        # Linux (and other): best-effort only.
        paths.append(Path.home() / ".config" / "Claude" / "claude_desktop_config.json")

    # De-dup while preserving order.
    seen: set[str] = set()
    unique: list[Path] = []
    for item in paths:
        key = str(item)
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return unique


def _discover_mcp_from_claude_desktop() -> list[MCPServerRecord]:
    """Discover MCP servers from Claude Desktop config (mcpServers)."""

    records: list[MCPServerRecord] = []
    for path in _default_claude_desktop_config_paths():
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        servers = payload.get("mcpServers", {})
        if not isinstance(servers, dict):
            continue

        for name, cfg in servers.items():
            if not isinstance(cfg, dict) or not name:
                continue
            transport = cfg.get("transport") or "stdio"
            command = cfg.get("command") or ""
            args = cfg.get("args") or []
            url = cfg.get("url") or ""
            env = cfg.get("env") or {}
            if not isinstance(args, list):
                args = []
            if not isinstance(env, dict):
                env = {}

            records.append(
                MCPServerRecord(
                    name=str(name),
                    transport=str(transport),
                    command=str(command),
                    args=[str(item) for item in args],
                    url=str(url),
                    env={str(k): str(v) for k, v in env.items()},
                    source="claude-desktop",
                )
            )
    return records


def _discover_mcp_from_claude_code_dir() -> list[MCPServerRecord]:
    """Discover MCP servers from Claude Code's ~/.claude/ directory.

    Covers two patterns:
    1. ~/.claude/settings.json (or settings-*.json) containing a top-level "mcpServers" dict
       (same structure as Claude Desktop's mcpServers).
    2. ~/.claude/mcp-servers/*.py — each .py file is treated as a stdio MCP server
       (server name = filename without extension, command = python <path>).
    """

    records: list[MCPServerRecord] = []
    claude_home = Path.home() / ".claude"
    if not claude_home.is_dir():
        return records

    # --- Pattern 1: settings*.json with mcpServers ---
    for settings_file in sorted(claude_home.glob("settings*.json")):
        try:
            payload = json.loads(settings_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        servers = payload.get("mcpServers", {})
        if not isinstance(servers, dict):
            continue
        for name, cfg in servers.items():
            if not isinstance(cfg, dict) or not name:
                continue
            transport = cfg.get("transport") or "stdio"
            command = cfg.get("command") or ""
            args = cfg.get("args") or []
            url = cfg.get("url") or ""
            env = cfg.get("env") or {}
            if not isinstance(args, list):
                args = []
            if not isinstance(env, dict):
                env = {}
            records.append(
                MCPServerRecord(
                    name=str(name),
                    transport=str(transport),
                    command=str(command),
                    args=[str(item) for item in args],
                    url=str(url),
                    env={str(k): str(v) for k, v in env.items()},
                    source="claude-code-settings",
                )
            )

    # --- Pattern 2: ~/.claude/mcp-servers/*.py ---
    mcp_servers_dir = claude_home / "mcp-servers"
    if mcp_servers_dir.is_dir():
        for py_file in sorted(mcp_servers_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            server_name = py_file.stem  # e.g. dameng_mcp.py -> dameng_mcp
            records.append(
                MCPServerRecord(
                    name=server_name,
                    transport="stdio",
                    command=sys.executable,
                    args=[str(py_file.resolve())],
                    source="claude-code-mcp-servers",
                )
            )

    return records


def _discover_mcp_from_project_manifest(project_root: Path) -> list[MCPServerRecord]:
    records: list[MCPServerRecord] = []
    local_manifest = project_root / ".mcp.json"
    if not local_manifest.exists():
        return records

    try:
        payload = json.loads(local_manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return records

    for server_name, server_config in payload.get("servers", {}).items():
        if not isinstance(server_config, dict) or not server_name:
            continue
        env = server_config.get("env") or {}
        if not isinstance(env, dict):
            env = {}
        records.append(
            MCPServerRecord(
                name=server_name,
                transport=server_config.get("transport", "stdio"),
                command=server_config.get("command", ""),
                args=server_config.get("args", []),
                url=server_config.get("url", ""),
                env={str(k): str(v) for k, v in env.items()},
                source="project-manifest",
            )
        )
    return records


def _merge_mcp_records(existing: list[MCPServerRecord], discovered: list[MCPServerRecord]) -> list[MCPServerRecord]:
    """Merge discovered MCP servers into registry without clobbering grants.

    - Preserve existing enabled/roles/models and per-tool grants (avoid losing allowlists).
    - Update transport/command/args/url/source from discovered.
    - Update env only if discovered provides it.
    - Merge tools by name:
      - Preserve existing tool enabled/roles/models/description.
      - Append newly discovered tools.
    """

    def _merge_tools(*, existing_tools: list[MCPToolRecord], discovered_tools: list[MCPToolRecord]) -> list[MCPToolRecord]:
        by_name: dict[str, MCPToolRecord] = {tool.name.lower(): tool for tool in existing_tools}
        for tool in discovered_tools:
            key = tool.name.lower()
            if key not in by_name:
                by_name[key] = tool
        merged_tools = list(by_name.values())
        merged_tools.sort(key=lambda t: t.name.lower())
        return merged_tools

    by_key: dict[str, MCPServerRecord] = {item.name.lower(): item for item in existing}

    for item in discovered:
        key = item.name.lower()
        current = by_key.get(key)
        if current is None:
            by_key[key] = item
            continue

        # Preserve grants/allowlists.
        preserved_enabled = current.enabled
        preserved_roles = list(current.roles)
        preserved_models = list(current.models)

        preserved_tools = list(current.tools)

        # Update connectivity details.
        current.transport = item.transport
        current.command = item.command
        current.args = list(item.args)
        current.url = item.url
        current.source = item.source
        if item.env:
            current.env = dict(item.env)

        current.enabled = preserved_enabled
        current.roles = preserved_roles
        current.models = preserved_models

        current.tools = _merge_tools(existing_tools=preserved_tools, discovered_tools=list(item.tools))

    merged = list(by_key.values())
    merged.sort(key=lambda r: r.name.lower())
    return merged


def _tool_record(
    name: str,
    description: str,
    *,
    read_only_hint: bool | None = None,
    destructive_hint: bool | None = None,
    idempotent_hint: bool | None = None,
    open_world_hint: bool | None = None,
) -> MCPToolRecord:
    return MCPToolRecord(
        name=name,
        description=description,
        read_only_hint=read_only_hint,
        destructive_hint=destructive_hint,
        idempotent_hint=idempotent_hint,
        open_world_hint=open_world_hint,
    )


def _build_builtin_mao_mcp() -> list[MCPServerRecord]:
    import sys

    mcp_entrypoint = ["-m", "mao_cli.main", "mcp-serve", "--transport", "stdio"]

    mao_mcp = MCPServerRecord(
        name="mao_mcp",
        transport="stdio",
        command=sys.executable,
        args=mcp_entrypoint,
        source="local-import",
        tools=[
            _tool_record("mao_project_status", "Read current project status.", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
            _tool_record("mao_read_project_doc", "Read one tracked project document.", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
            _tool_record("mao_list_runs", "List recent workflow runs.", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
            _tool_record("mao_read_run_summary", "Read a saved run summary.", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
            _tool_record("mao_list_sessions", "List saved chat sessions.", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
            _tool_record("mao_read_session", "Read one saved chat session.", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
            _tool_record("mao_list_skills", "List registered skills.", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
            _tool_record("mao_read_skill", "Read one registered skill.", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
            _tool_record("mao_list_mcp_servers", "List registered MCP servers.", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
            _tool_record("mao_read_mcp_server", "Read one registered MCP server.", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
            _tool_record("mao_write_team_note", "Append a team note.", read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False),
            _tool_record("mao_write_session_note", "Append a session note.", read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False),
            _tool_record("mao_trigger_mock_workflow", "Trigger mock workflow execution.", read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False),
        ],
    )

    mao_fs = MCPServerRecord(
        name="mao_fs",
        transport="stdio",
        command=sys.executable,
        args=mcp_entrypoint,
        source="local-import",
        roles=["architect"],
        tools=[
            _tool_record("mao_fs_find_paths", "Find paths by file or directory name. Args: {\"query\": \"<name>\", \"exact\": true}", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
            _tool_record("mao_fs_list_dir", "List directory. Args: {\"path\": \".\"}", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
            _tool_record("mao_fs_read_text", "Read text file. Args: {\"path\": \"<file>\"}", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
            _tool_record("mao_fs_write_text", "Write text file. Args: {\"path\": \"<file>\", \"content\": \"...\", \"overwrite\": true, \"confirm\": \"YES\"} (confirm required for overwrite)", read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False),
            _tool_record("mao_fs_mkdir", "Create directory. Args: {\"path\": \"<dir>\"}", read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
            _tool_record("mao_fs_delete_file", "Delete file. Args: {\"path\": \"<file>\", \"confirm\": \"DELETE\"} (confirm is REQUIRED)", read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False),
            _tool_record("mao_fs_delete_dir", "Delete directory. Args: {\"path\": \"<dir>\", \"confirm\": \"DELETE\", \"recursive\": true} (confirm is REQUIRED)", read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False),
        ],
    )

    return [mao_mcp, mao_fs]


def import_local_mcp(project_root: Path, runtime_root: str) -> Path:
    from mao_cli.mcp_client import list_mcp_tools_sync

    existing = load_mcp_registry(project_root, runtime_root)

    discovered: list[MCPServerRecord] = []
    discovered.extend(_build_builtin_mao_mcp())
    discovered.extend(_discover_mcp_from_project_manifest(project_root))
    discovered.extend(_discover_mcp_from_claude_desktop())
    discovered.extend(_discover_mcp_from_claude_code_dir())

    merged = _merge_mcp_records(existing, discovered)

    # Best-effort tool probing so models can see <server>.<tool> names.
    for record in merged:
        if record.tools:
            continue
        if not record.enabled:
            continue
        if record.transport == "stdio" and record.command:
            try:
                tools = list_mcp_tools_sync(record)
                record.tools = [
                    MCPToolRecord(
                        name=item.name,
                        description=item.description or "",
                        read_only_hint=getattr(item, "read_only_hint", None),
                        destructive_hint=getattr(item, "destructive_hint", None),
                        idempotent_hint=getattr(item, "idempotent_hint", None),
                        open_world_hint=getattr(item, "open_world_hint", None),
                    )
                    for item in tools
                    if item and getattr(item, "name", "")
                ]
                record.source = record.source or "local-import"
            except Exception:  # noqa: BLE001
                # Do not block imports if probing fails.
                record.tools = []
        elif record.transport == "streamable-http" and record.url:
            try:
                tools = list_mcp_tools_sync(record)
                record.tools = [
                    MCPToolRecord(
                        name=item.name,
                        description=item.description or "",
                        read_only_hint=getattr(item, "read_only_hint", None),
                        destructive_hint=getattr(item, "destructive_hint", None),
                        idempotent_hint=getattr(item, "idempotent_hint", None),
                        open_world_hint=getattr(item, "open_world_hint", None),
                    )
                    for item in tools
                    if item and getattr(item, "name", "")
                ]
            except Exception:  # noqa: BLE001
                record.tools = []

    return save_mcp_registry(project_root, runtime_root, merged)


def find_skill_record(project_root: Path, runtime_root: str, name: str) -> SkillRecord:
    target = name.strip().lower()
    for record in registered_or_discovered_skills(project_root, runtime_root):
        if record.name.lower() == target:
            return record
    raise FileNotFoundError(f"Skill `{name}` not found in registry.")


def find_mcp_record(project_root: Path, runtime_root: str, name: str) -> MCPServerRecord:
    target = name.strip().lower()
    for record in load_mcp_registry(project_root, runtime_root):
        if record.name.lower() == target:
            return record
    raise FileNotFoundError(f"MCP server `{name}` not found in registry.")


def assign_skill_access(
    project_root: Path,
    runtime_root: str,
    *,
    name: str,
    role: str | None = None,
    model: str | None = None,
) -> Path:
    records = load_skill_registry(project_root, runtime_root)
    for record in records:
        if record.name.lower() == name.lower():
            if role and role not in record.roles:
                record.roles.append(role)
            if model and model not in record.models:
                record.models.append(model)
            return save_skill_registry(project_root, runtime_root, records)
    raise FileNotFoundError(f"Skill `{name}` not found in registry.")


def bind_skill_to_mcp(
    project_root: Path,
    runtime_root: str,
    *,
    skill: str,
    server: str,
    tool: str,
) -> Path:
    records = load_skill_registry(project_root, runtime_root)
    for record in records:
        if record.name.lower() == skill.lower():
            record.mcp_server = server
            record.mcp_tool = tool
            return save_skill_registry(project_root, runtime_root, records)
    raise FileNotFoundError(f"Skill `{skill}` not found in registry.")


def register_skill(
    project_root: Path,
    runtime_root: str,
    *,
    name: str,
    description: str,
    path: str,
    source: str = "manual",
) -> Path:
    records = load_skill_registry(project_root, runtime_root)
    existing = next((record for record in records if record.name.lower() == name.lower()), None)
    if existing is None:
        records.append(SkillRecord(name=name, description=description, path=path, source=source))
    else:
        existing.description = description
        existing.path = path
        existing.source = source
    return save_skill_registry(project_root, runtime_root, records)


def assign_mcp_access(
    project_root: Path,
    runtime_root: str,
    *,
    name: str,
    role: str | None = None,
    model: str | None = None,
) -> Path:
    records = load_mcp_registry(project_root, runtime_root)
    for record in records:
        if record.name.lower() == name.lower():
            if role and role not in record.roles:
                record.roles.append(role)
            if model and model not in record.models:
                record.models.append(model)
            return save_mcp_registry(project_root, runtime_root, records)
    raise FileNotFoundError(f"MCP server `{name}` not found in registry.")


def register_mcp_server(
    project_root: Path,
    runtime_root: str,
    *,
    name: str,
    transport: str,
    command: str = "",
    args: list[str] | None = None,
    url: str = "",
    env: dict[str, str] | None = None,
    source: str = "manual",
) -> Path:
    records = load_mcp_registry(project_root, runtime_root)
    existing = next((record for record in records if record.name.lower() == name.lower()), None)
    payload = MCPServerRecord(
        name=name,
        transport=transport,
        command=command,
        args=args or [],
        url=url,
        env=env or {},
        source=source,
    )
    if existing is None:
        records.append(payload)
    else:
        existing.transport = payload.transport
        existing.command = payload.command
        existing.args = payload.args
        existing.url = payload.url
        existing.source = payload.source
        if env is not None:
            existing.env = dict(env)
    return save_mcp_registry(project_root, runtime_root, records)
