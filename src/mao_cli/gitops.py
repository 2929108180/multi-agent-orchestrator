from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel


class WorkerWorkspace(BaseModel):
    role: str
    path: str
    git_ref: str


def _run_git(args: list[str], workdir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=workdir,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def verify_git_repository(repository_root: Path) -> None:
    result = _run_git(["rev-parse", "--show-toplevel"], repository_root)
    if result.returncode != 0:
        raise RuntimeError(f"`{repository_root}` is not a git repository: {result.stderr.strip()}")


def create_worker_worktrees(
    repository_root: Path,
    workspace_root: Path,
    run_id: str,
    roles: list[str],
    git_ref: str = "HEAD",
) -> list[WorkerWorkspace]:
    verify_git_repository(repository_root)
    run_workspace_root = workspace_root / run_id
    run_workspace_root.mkdir(parents=True, exist_ok=True)

    workspaces: list[WorkerWorkspace] = []
    for role in roles:
        role_path = run_workspace_root / role
        role_path.parent.mkdir(parents=True, exist_ok=True)
        result = _run_git(["worktree", "add", "--detach", str(role_path), git_ref], repository_root)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"Failed to create worktree for `{role}`: {stderr}")
        workspaces.append(
            WorkerWorkspace(
                role=role,
                path=str(role_path),
                git_ref=git_ref,
            )
        )
    return workspaces


def ensure_named_worktree(
    repository_root: Path,
    workspace_root: Path,
    worktree_name: str,
    git_ref: str = "HEAD",
) -> WorkerWorkspace:
    verify_git_repository(repository_root)
    role_path = workspace_root / worktree_name
    role_path.parent.mkdir(parents=True, exist_ok=True)
    if role_path.exists():
        return WorkerWorkspace(role=worktree_name, path=str(role_path), git_ref=git_ref)
    result = _run_git(["worktree", "add", "--detach", str(role_path), git_ref], repository_root)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"Failed to create worktree for `{worktree_name}`: {stderr}")
    return WorkerWorkspace(role=worktree_name, path=str(role_path), git_ref=git_ref)


def write_worker_note(workspace: WorkerWorkspace, content: str, filename: str = "WORKER_NOTES.md") -> Path:
    note_path = Path(workspace.path) / filename
    note_path.write_text(content, encoding="utf-8")
    return note_path


def apply_proposal_to_workspace(
    workspace: WorkerWorkspace,
    relative_path: str,
    proposal_path: str | Path,
) -> Path:
    target_path = Path(workspace.path) / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    content = Path(proposal_path).read_text(encoding="utf-8")
    target_path.write_text(content, encoding="utf-8")
    return target_path
