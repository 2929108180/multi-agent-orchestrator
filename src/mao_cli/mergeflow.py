from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field


class MergeCandidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: str
    item_id: str
    role: str
    path: str
    model: str
    integration_workspace: str
    applied_path: str
    shared_file: bool = False
    status: str = "ready_for_merge"
    reason: str = ""


def merge_registry_path(project_root: Path, runtime_root: str) -> Path:
    root = project_root / runtime_root / "merge"
    root.mkdir(parents=True, exist_ok=True)
    return root / "merge_candidates.json"


def load_merge_candidates(project_root: Path, runtime_root: str) -> list[MergeCandidate]:
    path = merge_registry_path(project_root, runtime_root)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [MergeCandidate.model_validate(item) for item in payload]


def save_merge_candidates(project_root: Path, runtime_root: str, candidates: list[MergeCandidate]) -> Path:
    path = merge_registry_path(project_root, runtime_root)
    path.write_text(
        json.dumps([candidate.model_dump(mode="json") for candidate in candidates], indent=2),
        encoding="utf-8",
    )
    return path


def append_merge_candidate(project_root: Path, runtime_root: str, candidate: MergeCandidate) -> Path:
    candidates = load_merge_candidates(project_root, runtime_root)
    candidates.append(candidate)
    return save_merge_candidates(project_root, runtime_root, candidates)


def list_merge_candidates(project_root: Path, runtime_root: str, limit: int = 50) -> list[MergeCandidate]:
    candidates = load_merge_candidates(project_root, runtime_root)
    return sorted(candidates, key=lambda item: item.created_at, reverse=True)[:limit]
