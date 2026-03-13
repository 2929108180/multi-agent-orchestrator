from __future__ import annotations

import json
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


class MCPToolRecord(BaseModel):
    name: str
    description: str
    enabled: bool = True
    roles: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)


class MCPServerRecord(BaseModel):
    name: str
    transport: str
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str = ""
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


def load_mcp_registry(project_root: Path, runtime_root: str) -> list[MCPServerRecord]:
    path = mcp_registry_path(project_root, runtime_root)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [MCPServerRecord.model_validate(item) for item in payload]


def save_mcp_registry(project_root: Path, runtime_root: str, records: list[MCPServerRecord]) -> Path:
    path = mcp_registry_path(project_root, runtime_root)
    path.write_text(
        json.dumps([record.model_dump() for record in records], indent=2),
        encoding="utf-8",
    )
    return path


def import_local_mcp(project_root: Path, runtime_root: str) -> Path:
    records = [
        MCPServerRecord(
            name="mao_mcp",
            transport="stdio",
            command="mao",
            args=["mcp-serve", "--transport", "stdio"],
            source="local-import",
            tools=[
                MCPToolRecord(name="mao_project_status", description="Read current project status."),
                MCPToolRecord(name="mao_read_project_doc", description="Read one tracked project document."),
                MCPToolRecord(name="mao_list_runs", description="List recent workflow runs."),
                MCPToolRecord(name="mao_read_run_summary", description="Read a saved run summary."),
                MCPToolRecord(name="mao_list_sessions", description="List saved chat sessions."),
                MCPToolRecord(name="mao_read_session", description="Read one saved chat session."),
                MCPToolRecord(name="mao_list_skills", description="List registered skills."),
                MCPToolRecord(name="mao_read_skill", description="Read one registered skill."),
                MCPToolRecord(name="mao_write_team_note", description="Append a team note."),
                MCPToolRecord(name="mao_write_session_note", description="Append a session note."),
                MCPToolRecord(name="mao_trigger_mock_workflow", description="Trigger mock workflow execution."),
            ],
        )
    ]
    local_manifest = project_root / ".mcp.json"
    if local_manifest.exists():
        try:
            payload = json.loads(local_manifest.read_text(encoding="utf-8"))
            for server_name, server_config in payload.get("servers", {}).items():
                records.append(
                    MCPServerRecord(
                        name=server_name,
                        transport=server_config.get("transport", "stdio"),
                        command=server_config.get("command", ""),
                        args=server_config.get("args", []),
                        url=server_config.get("url", ""),
                        source="project-manifest",
                    )
                )
        except json.JSONDecodeError:
            pass
    return save_mcp_registry(project_root, runtime_root, records)


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
    return save_mcp_registry(project_root, runtime_root, records)
