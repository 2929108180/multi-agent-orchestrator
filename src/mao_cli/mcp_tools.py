from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from mao_cli.config import load_config
from mao_cli.orchestrator import execute_workflow
from mao_cli.registry import (
    find_mcp_record,
    find_skill_record,
    load_mcp_registry,
    registered_or_discovered_skills,
)
from mao_cli.sessions import append_session_note, list_sessions, load_session
from mao_cli.security import ensure_project_path, validate_requirement, validate_run_id
from mao_cli.skills import append_team_note


class RunListItem(BaseModel):
    run_id: str
    created_at: str | None = None
    approved: bool | None = None
    summary: str = ""
    path: str


class WorkflowTriggerResult(BaseModel):
    run_id: str
    run_dir: str
    summary_path: str
    approved: bool | None = None


class SessionListItem(BaseModel):
    session_id: str
    updated_at: str
    mode: str
    turns: int


class SkillListItem(BaseModel):
    name: str
    description: str
    path: str


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def project_status_text() -> str:
    progress_path = _project_root() / "docs" / "progress.md"
    return progress_path.read_text(encoding="utf-8")


def read_project_doc(doc_name: str) -> str:
    allowed_docs = {
        "architecture-baseline": "architecture-baseline.md",
        "progress": "progress.md",
        "technical-design-v1": "technical-design-v1.md",
        "v1-target": "v1-target.md",
    }
    if doc_name not in allowed_docs:
        names = ", ".join(sorted(allowed_docs))
        raise ValueError(f"Unsupported document `{doc_name}`. Allowed values: {names}")
    doc_path = _project_root() / "docs" / allowed_docs[doc_name]
    return doc_path.read_text(encoding="utf-8")


def list_runs(limit: int = 10, *, config_path: str = "configs/local.example.yaml") -> list[RunListItem]:
    project_root = _project_root()
    absolute_config = ensure_project_path(
        project_root,
        config_path,
        must_exist=True,
        label="config_path",
    )
    config = load_config(absolute_config)
    runs_root = project_root / config.artifacts_root / "runs"
    if not runs_root.exists():
        return []

    items: list[RunListItem] = []
    for run_dir in sorted(
        [item for item in runs_root.iterdir() if item.is_dir()],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )[:limit]:
        run_json = run_dir / "run.json"
        summary = run_dir / "summary.md"
        created_at = None
        approved = None
        summary_text = ""
        if run_json.exists():
            payload = json.loads(run_json.read_text(encoding="utf-8"))
            created_at = payload.get("created_at")
            verdicts = payload.get("verdicts") or []
            if verdicts:
                approved = verdicts[-1].get("approved")
        if summary.exists():
            summary_lines = summary.read_text(encoding="utf-8").splitlines()
            summary_text = summary_lines[0] if summary_lines else ""

        items.append(
            RunListItem(
                run_id=run_dir.name,
                created_at=created_at,
                approved=approved,
                summary=summary_text,
                path=str(run_dir),
            )
        )
    return items


def read_run_summary(run_id: str, *, config_path: str = "configs/local.example.yaml") -> str:
    safe_run_id = validate_run_id(run_id)
    project_root = _project_root()
    absolute_config = ensure_project_path(
        project_root,
        config_path,
        must_exist=True,
        label="config_path",
    )
    config = load_config(absolute_config)
    summary_path = project_root / config.artifacts_root / "runs" / safe_run_id / "summary.md"
    if not summary_path.exists():
        raise FileNotFoundError(f"Run summary not found for `{safe_run_id}`.")
    return summary_path.read_text(encoding="utf-8")


def list_saved_sessions(limit: int = 10, *, config_path: str = "configs/local.example.yaml") -> list[SessionListItem]:
    project_root = _project_root()
    absolute_config = ensure_project_path(
        project_root,
        config_path,
        must_exist=True,
        label="config_path",
    )
    runtime_root = load_config(absolute_config).runtime_root
    sessions = list_sessions(project_root, runtime_root, limit=limit)
    return [
        SessionListItem(
            session_id=session.session_id,
            updated_at=session.updated_at.isoformat(),
            mode=session.mode,
            turns=len(session.turns),
        )
        for session in sessions
    ]


def read_saved_session(session_id: str, *, config_path: str = "configs/local.example.yaml") -> str:
    project_root = _project_root()
    absolute_config = ensure_project_path(
        project_root,
        config_path,
        must_exist=True,
        label="config_path",
    )
    runtime_root = load_config(absolute_config).runtime_root
    session = load_session(project_root, runtime_root, session_id)
    return json.dumps(session.model_dump(mode="json"), indent=2)


def list_available_skills(*, config_path: str = "configs/local.example.yaml") -> list[SkillListItem]:
    project_root = _project_root()
    absolute_config = ensure_project_path(
        project_root,
        config_path,
        must_exist=True,
        label="config_path",
    )
    runtime_root = load_config(absolute_config).runtime_root
    return [
        SkillListItem(name=entry.name, description=entry.description, path=entry.path)
        for entry in registered_or_discovered_skills(project_root, runtime_root)
    ]


def read_available_skill(skill_name: str, *, config_path: str = "configs/local.example.yaml") -> str:
    project_root = _project_root()
    absolute_config = ensure_project_path(
        project_root,
        config_path,
        must_exist=True,
        label="config_path",
    )
    runtime_root = load_config(absolute_config).runtime_root
    entry = find_skill_record(project_root, runtime_root, skill_name)
    return json.dumps(entry.model_dump(), indent=2)


def list_registered_mcp_servers(*, config_path: str = "configs/local.example.yaml") -> list[dict[str, str | bool]]:
    project_root = _project_root()
    absolute_config = ensure_project_path(
        project_root,
        config_path,
        must_exist=True,
        label="config_path",
    )
    runtime_root = load_config(absolute_config).runtime_root
    return [record.model_dump() for record in load_mcp_registry(project_root, runtime_root)]


def read_registered_mcp_server(name: str, *, config_path: str = "configs/local.example.yaml") -> str:
    project_root = _project_root()
    absolute_config = ensure_project_path(
        project_root,
        config_path,
        must_exist=True,
        label="config_path",
    )
    runtime_root = load_config(absolute_config).runtime_root
    record = find_mcp_record(project_root, runtime_root, name)
    return json.dumps(record.model_dump(), indent=2)


def write_team_note(note: str, category: str = "general", *, config_path: str = "configs/local.example.yaml") -> str:
    project_root = _project_root()
    absolute_config = ensure_project_path(
        project_root,
        config_path,
        must_exist=True,
        label="config_path",
    )
    runtime_root = load_config(absolute_config).runtime_root
    path = append_team_note(project_root, runtime_root, note, category=category)
    return str(path)


def write_session_note(session_id: str, note: str, *, config_path: str = "configs/local.example.yaml") -> str:
    project_root = _project_root()
    absolute_config = ensure_project_path(
        project_root,
        config_path,
        must_exist=True,
        label="config_path",
    )
    runtime_root = load_config(absolute_config).runtime_root
    path = append_session_note(project_root, runtime_root, session_id, note)
    return str(path)


def trigger_mock_workflow(
    requirement: str,
    config_path: str = "configs/local.example.yaml",
    with_worktrees: bool = False,
) -> WorkflowTriggerResult:
    project_root = _project_root()
    requirement = validate_requirement(requirement)
    absolute_config = ensure_project_path(
        project_root,
        config_path,
        must_exist=True,
        label="config_path",
    )
    config = load_config(absolute_config)
    output_dir = project_root / config.artifacts_root / "runs"
    run_dir = execute_workflow(
        requirement=requirement,
        config=config,
        output_dir=output_dir,
        repository_root=project_root,
        force_mock=True,
        with_worktrees=with_worktrees,
    )
    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    verdicts = payload.get("verdicts") or []
    approved = verdicts[-1].get("approved") if verdicts else None
    return WorkflowTriggerResult(
        run_id=payload["run_id"],
        run_dir=str(run_dir),
        summary_path=str(run_dir / "summary.md"),
        approved=approved,
    )
