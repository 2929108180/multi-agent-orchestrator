from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mcp.server.fastmcp import FastMCP

from mao_cli.mcp_tools import (
    fs_find_paths,
    fs_delete_dir,
    fs_delete_file,
    fs_list_dir,
    fs_mkdir,
    fs_read_text,
    fs_write_text,
    list_available_skills,
    list_registered_mcp_servers,
    list_runs,
    list_saved_sessions,
    project_status_text,
    read_available_skill,
    read_project_doc,
    read_registered_mcp_server,
    read_run_summary,
    read_saved_session,
    trigger_mock_workflow,
    write_session_note,
    write_team_note,
)

mcp = FastMCP("mao_mcp", json_response=True)


class DocInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    doc_name: str = Field(
        ...,
        description="Document name: architecture-baseline, progress, technical-design-v1, or v1-target.",
        min_length=1,
    )


class RunListInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    limit: int = Field(default=10, ge=1, le=20, description="Maximum number of runs to return.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls artifacts_root).",
    )


class RunSummaryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    run_id: str = Field(..., min_length=4, description="Run identifier, for example `efd86dfab9c5`.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls artifacts_root).",
    )


class TriggerWorkflowInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    requirement: str = Field(..., min_length=3, description="Requirement to execute in mock workflow mode.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config.",
    )
    with_worktrees: bool = Field(
        default=False,
        description="When true, create isolated frontend/backend git worktrees for the run.",
    )


class SessionListInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    limit: int = Field(default=10, ge=1, le=20, description="Maximum number of saved sessions to return.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls runtime_root).",
    )


class SessionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    session_id: str = Field(..., min_length=4, description="Saved session identifier.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls runtime_root).",
    )


class SkillListInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls runtime_root).",
    )


class SkillInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    skill_name: str = Field(..., min_length=1, description="Skill name to read.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls runtime_root).",
    )


class MCPListInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls runtime_root).",
    )


class MCPReadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    name: str = Field(..., min_length=1, description="MCP server name to read.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls runtime_root).",
    )


class FSListDirInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    path: str = Field(default=".", description="Directory path relative to project root.")


class FSFindPathsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    query: str = Field(..., min_length=1, description="Filename or directory name to search for.")
    exact: bool = Field(default=False, description="When true, match the entry name exactly.")
    include_files: bool = Field(default=True, description="Include files in results.")
    include_dirs: bool = Field(default=True, description="Include directories in results.")
    max_results: int = Field(default=20, ge=1, le=200, description="Maximum number of matches to return.")


class FSReadTextInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    path: str = Field(..., min_length=1, description="File path relative to project root.")
    max_chars: int = Field(default=200000, ge=1, le=2000000, description="Max characters to return.")


class FSWriteTextInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    path: str = Field(..., min_length=1, description="File path relative to project root.")
    content: str = Field(..., description="UTF-8 text content to write.")
    overwrite: bool = Field(default=False, description="When true, allow overwriting existing file.")
    confirm: str = Field(default="", description="Required when overwrite=true: must be 'YES'.")
    mkdir_parents: bool = Field(default=True, description="When true, create parent directories.")


class FSMkdirInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    path: str = Field(..., min_length=1, description="Directory path relative to project root.")
    parents: bool = Field(default=True, description="Create parent directories.")
    exist_ok: bool = Field(default=True, description="Allow existing directory.")


class FSDeleteFileInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    path: str = Field(..., min_length=1, description="File path relative to project root.")
    confirm: str = Field(..., description="Must be 'DELETE' to proceed.")


class FSDeleteDirInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    path: str = Field(..., min_length=1, description="Directory path relative to project root.")
    confirm: str = Field(..., description="Must be 'DELETE' to proceed.")
    recursive: bool = Field(default=False, description="When true, delete directory contents recursively.")


class TeamNoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    note: str = Field(..., min_length=1, description="Team note content to append under runtime/team.")
    category: str = Field(default="general", min_length=1, description="Category name for the team note file.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls runtime_root).",
    )


class SessionNoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    session_id: str = Field(..., min_length=4, description="Saved session identifier.")
    note: str = Field(..., min_length=1, description="Note content to append to the saved session.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls runtime_root).",
    )


@mcp.tool(
    name="mao_project_status",
    annotations={
        "title": "Read Project Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def mao_project_status() -> str:
    """Read the current project progress document."""
    return project_status_text()


@mcp.tool(
    name="mao_read_project_doc",
    annotations={
        "title": "Read Project Document",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def mao_read_project_doc(params: DocInput) -> str:
    """Read one of the tracked project documents by stable name."""
    return read_project_doc(params.doc_name)


@mcp.tool(
    name="mao_list_runs",
    annotations={
        "title": "List Workflow Runs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def mao_list_runs(params: RunListInput) -> list[dict[str, str | bool | None]]:
    """List the most recent workflow runs and their approval state."""
    return [item.model_dump() for item in list_runs(limit=params.limit, config_path=params.config_path)]


@mcp.tool(
    name="mao_read_run_summary",
    annotations={
        "title": "Read Run Summary",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def mao_read_run_summary(params: RunSummaryInput) -> str:
    """Read the markdown summary for a saved workflow run."""
    return read_run_summary(params.run_id, config_path=params.config_path)


@mcp.tool(
    name="mao_list_sessions",
    annotations={
        "title": "List Saved Sessions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def mao_list_sessions(params: SessionListInput) -> list[dict[str, str | int]]:
    """List saved local chat sessions."""
    return [
        item.model_dump()
        for item in list_saved_sessions(limit=params.limit, config_path=params.config_path)
    ]


@mcp.tool(
    name="mao_read_session",
    annotations={
        "title": "Read Saved Session",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def mao_read_session(params: SessionInput) -> str:
    """Read one saved local chat session as JSON."""
    return read_saved_session(params.session_id, config_path=params.config_path)


@mcp.tool(
    name="mao_list_skills",
    annotations={
        "title": "List Available Skills",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def mao_list_skills(params: SkillListInput) -> list[dict[str, str]]:
    """List discovered local skills available for team mode."""
    return [item.model_dump() for item in list_available_skills(config_path=params.config_path)]


@mcp.tool(
    name="mao_read_skill",
    annotations={
        "title": "Read Skill Entry",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def mao_read_skill(params: SkillInput) -> str:
    """Read a single discovered skill entry."""
    return read_available_skill(params.skill_name, config_path=params.config_path)


@mcp.tool(
    name="mao_list_mcp_servers",
    annotations={
        "title": "List Registered MCP Servers",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def mao_list_mcp_servers(params: MCPListInput) -> str:
    """List registered MCP servers (including built-ins and imports). Returns JSON."""
    return list_registered_mcp_servers(config_path=params.config_path)


@mcp.tool(
    name="mao_read_mcp_server",
    annotations={
        "title": "Read Registered MCP Server",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def mao_read_mcp_server(params: MCPReadInput) -> str:
    """Read one registered MCP server record as JSON."""
    return read_registered_mcp_server(params.name, config_path=params.config_path)


@mcp.tool(
    name="mao_fs_find_paths",
    annotations={
        "title": "Find Paths",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def mao_fs_find_paths(params: FSFindPathsInput) -> str:
    """Find files or directories under the project root by name. Returns JSON."""
    import json as _json
    return _json.dumps(
        [item.model_dump() for item in fs_find_paths(
            params.query,
            exact=params.exact,
            include_files=params.include_files,
            include_dirs=params.include_dirs,
            max_results=params.max_results,
        )],
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool(
    name="mao_fs_list_dir",
    annotations={
        "title": "List Directory",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def mao_fs_list_dir(params: FSListDirInput) -> str:
    """List directory entries under the project root. Returns JSON."""
    import json as _json
    return _json.dumps([item.model_dump() for item in fs_list_dir(params.path)], indent=2, ensure_ascii=False)


@mcp.tool(
    name="mao_fs_read_text",
    annotations={
        "title": "Read Text File",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def mao_fs_read_text(params: FSReadTextInput) -> str:
    """Read a UTF-8 text file under the project root."""
    return fs_read_text(params.path, max_chars=params.max_chars)


@mcp.tool(
    name="mao_fs_write_text",
    annotations={
        "title": "Write Text File",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def mao_fs_write_text(params: FSWriteTextInput) -> str:
    """Write a UTF-8 text file under the project root."""
    return fs_write_text(
        params.path,
        params.content,
        overwrite=params.overwrite,
        confirm=params.confirm,
        mkdir_parents=params.mkdir_parents,
    )


@mcp.tool(
    name="mao_fs_mkdir",
    annotations={
        "title": "Create Directory",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def mao_fs_mkdir(params: FSMkdirInput) -> str:
    """Create a directory under the project root."""
    return fs_mkdir(params.path, parents=params.parents, exist_ok=params.exist_ok)


@mcp.tool(
    name="mao_fs_delete_file",
    annotations={
        "title": "Delete File",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def mao_fs_delete_file(params: FSDeleteFileInput) -> str:
    """Delete a file under the project root (requires confirm=DELETE)."""
    return fs_delete_file(params.path, confirm=params.confirm)


@mcp.tool(
    name="mao_fs_delete_dir",
    annotations={
        "title": "Delete Directory",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def mao_fs_delete_dir(params: FSDeleteDirInput) -> str:
    """Delete a directory under the project root (requires confirm=DELETE)."""
    return fs_delete_dir(params.path, confirm=params.confirm, recursive=params.recursive)


@mcp.tool(
    name="mao_trigger_mock_workflow",
    annotations={
        "title": "Trigger Mock Workflow",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def mao_trigger_mock_workflow(params: TriggerWorkflowInput) -> dict[str, str | bool | None]:
    """Run the local mock workflow and persist a new set of run artifacts."""
    result = trigger_mock_workflow(
        requirement=params.requirement,
        config_path=params.config_path,
        with_worktrees=params.with_worktrees,
    )
    return result.model_dump()


@mcp.tool(
    name="mao_write_team_note",
    annotations={
        "title": "Append Team Note",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def mao_write_team_note(params: TeamNoteInput) -> str:
    """Append a safe team note under runtime/team for local coordination."""
    return write_team_note(
        note=params.note,
        category=params.category,
        config_path=params.config_path,
    )


@mcp.tool(
    name="mao_write_session_note",
    annotations={
        "title": "Append Session Note",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def mao_write_session_note(params: SessionNoteInput) -> str:
    """Append a note to a saved local chat session."""
    return write_session_note(
        session_id=params.session_id,
        note=params.note,
        config_path=params.config_path,
    )


def run_mcp_server(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000) -> None:
    if transport == "streamable-http":
        mcp.run(transport=transport, host=host, port=port)
        return
    mcp.run(transport=transport)
