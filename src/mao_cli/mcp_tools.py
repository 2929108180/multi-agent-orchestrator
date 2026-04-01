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


def _reject_git_paths(path: Path, *, label: str = "path") -> None:
    parts = {part.lower() for part in path.parts}
    if ".git" in parts:
        raise ValueError(f"{label} cannot point inside .git")


def _project_safe_path(relative_or_abs: str | Path, *, must_exist: bool, label: str) -> Path:
    project_root = _project_root()
    resolved = ensure_project_path(project_root, relative_or_abs, must_exist=must_exist, label=label)
    _reject_git_paths(resolved, label=label)
    return resolved

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


class FSPathMatch(BaseModel):
    path: str
    is_dir: bool


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


def list_registered_mcp_servers(*, config_path: str = "configs/local.example.yaml") -> str:
    project_root = _project_root()
    absolute_config = ensure_project_path(
        project_root,
        config_path,
        must_exist=True,
        label="config_path",
    )
    runtime_root = load_config(absolute_config).runtime_root
    summary = []
    for record in load_mcp_registry(project_root, runtime_root):
        tool_names = [t.name for t in record.tools] if record.tools else []
        summary.append({
            "name": record.name,
            "transport": record.transport,
            "enabled": record.enabled,
            "source": record.source,
            "tools": tool_names,
        })
    return json.dumps(summary, indent=2, ensure_ascii=False)


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


class FSListDirItem(BaseModel):
    name: str
    path: str
    is_dir: bool


def fs_list_dir(path: str = ".") -> list[FSListDirItem]:
    target = _project_safe_path(path, must_exist=True, label="path")
    if not target.exists():
        raise FileNotFoundError(f"Directory not found: {path}")
    if not target.is_dir():
        raise ValueError(f"path must be a directory: {path}")

    items: list[FSListDirItem] = []
    for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        items.append(
            FSListDirItem(
                name=child.name,
                path=str(child.relative_to(_project_root())),
                is_dir=child.is_dir(),
            )
        )
    return items


def _project_relative_path(path: Path) -> str:
    return str(path.relative_to(_project_root()))


def _find_project_paths(
    query: str,
    *,
    exact: bool = False,
    include_files: bool = True,
    include_dirs: bool = True,
    max_results: int = 50,
) -> list[FSPathMatch]:
    project_root = _project_root()
    needle = query.strip().lower()
    if not needle:
        raise ValueError("query must not be empty")

    matches: list[FSPathMatch] = []
    for candidate in project_root.rglob("*"):
        if len(matches) >= max_results:
            break
        try:
            _reject_git_paths(candidate, label="path")
        except ValueError:
            continue
        name = candidate.name.lower()
        name_match = name == needle if exact else needle in name
        if not name_match:
            continue
        if candidate.is_file() and include_files:
            matches.append(FSPathMatch(path=_project_relative_path(candidate), is_dir=False))
            continue
        if candidate.is_dir() and include_dirs:
            matches.append(FSPathMatch(path=_project_relative_path(candidate), is_dir=True))
    return matches


def fs_find_paths(
    query: str,
    *,
    exact: bool = False,
    include_files: bool = True,
    include_dirs: bool = True,
    max_results: int = 50,
) -> list[FSPathMatch]:
    return _find_project_paths(
        query,
        exact=exact,
        include_files=include_files,
        include_dirs=include_dirs,
        max_results=max_results,
    )


def _numbered_lines(text: str) -> str:
    """Format text with line numbers like cat -n."""
    lines = text.splitlines()
    width = len(str(len(lines))) if lines else 1
    return "\n".join(f"{i + 1:>{width}}  {line}" for i, line in enumerate(lines))


def _diff_text(*, old: str, new: str, path: str) -> str:
    """Generate a unified-diff-style output for file changes."""
    import difflib

    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    fromfile = "/dev/null" if not old_lines else f"a/{path}"
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=fromfile, tofile=f"b/{path}")
    return "".join(diff)


def fs_read_text(path: str, *, max_chars: int = 200000) -> str:
    target = _project_safe_path(path, must_exist=True, label="path")
    if not target.is_file():
        raise ValueError(f"path must be a file: {path}")
    text = target.read_text(encoding="utf-8")
    if len(text) > max_chars:
        text = text[: max_chars - 3] + "..."
    rel = str(target.relative_to(_project_root()))
    return f"--- {rel} ---\n{_numbered_lines(text)}"


def fs_write_text(
    path: str,
    content: str,
    *,
    overwrite: bool = False,
    confirm: str = "",
    mkdir_parents: bool = True,
) -> str:
    target = _project_safe_path(path, must_exist=False, label="path")
    rel = _project_relative_path(target)

    old_text = ""
    is_overwrite = False
    if target.exists():
        if not overwrite:
            raise FileExistsError(f"File already exists: {path}. Set overwrite=true to replace it.")
        if confirm != "YES":
            raise ValueError("Refusing to overwrite without confirm=\"YES\".")
        old_text = target.read_text(encoding="utf-8")
        is_overwrite = True
    else:
        raw_path = str(path)
        is_bare_name = "/" not in raw_path and "\\" not in raw_path
        if is_bare_name:
            collisions = [
                item.path
                for item in _find_project_paths(
                    target.name,
                    exact=True,
                    include_files=True,
                    include_dirs=False,
                    max_results=10,
                )
                if item.path != rel
            ]
            if collisions:
                preview = ", ".join(collisions[:5])
                raise ValueError(
                    f"Ambiguous path `{path}`. Existing matches: {preview}. "
                    "Use the exact relative path instead of a bare filename."
                )

    if mkdir_parents:
        target.parent.mkdir(parents=True, exist_ok=True)
    elif not target.parent.exists():
        raise FileNotFoundError(f"Parent directory does not exist: {target.parent}")

    target.write_text(content, encoding="utf-8")

    diff = _diff_text(old=old_text, new=content, path=rel)
    if is_overwrite:
        return f"overwrite {rel}\n{diff}" if diff else f"overwrite {rel} (no changes)"
    return f"create {rel}\n{diff}" if diff else f"create {rel} (empty file)"


def fs_mkdir(path: str, *, parents: bool = True, exist_ok: bool = True) -> str:
    target = _project_safe_path(path, must_exist=False, label="path")
    target.mkdir(parents=parents, exist_ok=exist_ok)
    return str(target.relative_to(_project_root()))


def fs_delete_file(path: str, *, confirm: str) -> str:
    if confirm != "DELETE":
        raise ValueError("Refusing to delete without confirm=\"DELETE\".")
    target = _project_safe_path(path, must_exist=True, label="path")
    if target == _project_root().resolve():
        raise ValueError("Refusing to delete the project root.")
    if not target.is_file():
        raise ValueError(f"path must be a file: {path}")
    target.unlink()
    return str(target.relative_to(_project_root()))


def fs_delete_dir(path: str, *, confirm: str, recursive: bool = False) -> str:
    if confirm != "DELETE":
        raise ValueError("Refusing to delete without confirm=\"DELETE\".")
    target = _project_safe_path(path, must_exist=True, label="path")
    if target == _project_root().resolve():
        raise ValueError("Refusing to delete the project root.")
    if not target.is_dir():
        raise ValueError(f"path must be a directory: {path}")

    if recursive:
        # Manual recursive delete to avoid accidentally following symlinks outside the project.
        for child in sorted(target.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if child.is_dir():
                child.rmdir()
            else:
                child.unlink()
        target.rmdir()
        return str(target.relative_to(_project_root()))

    target.rmdir()
    return str(target.relative_to(_project_root()))


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
