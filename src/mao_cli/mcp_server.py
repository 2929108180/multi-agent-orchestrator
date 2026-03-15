from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mcp.server.fastmcp import FastMCP

from mao_cli.mcp_tools import (
    list_available_skills,
    list_runs,
    list_saved_sessions,
    project_status_text,
    read_available_skill,
    read_project_doc,
    read_run_summary,
    read_saved_session,
    trigger_mock_workflow,
    write_session_note,
    write_team_note,
)

mcp = FastMCP("mao_mcp", json_response=True)


class DocInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    doc_name: str = Field(
        ...,
        description="Document name: architecture-baseline, progress, technical-design-v1, or v1-target.",
        min_length=1,
    )


class RunListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=10, ge=1, le=20, description="Maximum number of runs to return.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls artifacts_root).",
    )


class RunSummaryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    run_id: str = Field(..., min_length=4, description="Run identifier, for example `efd86dfab9c5`.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls artifacts_root).",
    )


class TriggerWorkflowInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=10, ge=1, le=20, description="Maximum number of saved sessions to return.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls runtime_root).",
    )


class SessionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    session_id: str = Field(..., min_length=4, description="Saved session identifier.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls runtime_root).",
    )


class SkillListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls runtime_root).",
    )


class SkillInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    skill_name: str = Field(..., min_length=1, description="Skill name to read.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls runtime_root).",
    )


class TeamNoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    note: str = Field(..., min_length=1, description="Team note content to append under runtime/team.")
    category: str = Field(default="general", min_length=1, description="Category name for the team note file.")
    config_path: str = Field(
        default="configs/local.example.yaml",
        description="Relative or absolute path to a workflow config (controls runtime_root).",
    )


class SessionNoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

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
