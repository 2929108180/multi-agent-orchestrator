from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mcp.server.fastmcp import FastMCP

from mao_cli.mcp_tools import (
    list_runs,
    project_status_text,
    read_project_doc,
    read_run_summary,
    trigger_mock_workflow,
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


class RunSummaryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    run_id: str = Field(..., min_length=4, description="Run identifier, for example `efd86dfab9c5`.")


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
    return [item.model_dump() for item in list_runs(limit=params.limit)]


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
    return read_run_summary(params.run_id)


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


def run_mcp_server(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000) -> None:
    if transport == "streamable-http":
        mcp.run(transport=transport, host=host, port=port)
        return
    mcp.run(transport=transport)
