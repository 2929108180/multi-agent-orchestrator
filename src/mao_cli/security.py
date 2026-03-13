from __future__ import annotations

import re
from pathlib import Path

MAX_REQUIREMENT_LENGTH = 4000
MAX_DEFECT_TEXT_LENGTH = 1200
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{4,64}$")


def ensure_project_path(
    project_root: Path,
    candidate: str | Path,
    *,
    must_exist: bool = True,
    label: str = "path",
) -> Path:
    root = project_root.resolve()
    raw = Path(candidate)
    resolved = raw.resolve(strict=must_exist) if raw.is_absolute() else (root / raw).resolve(strict=must_exist)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside the project root: {resolved}") from exc
    return resolved


def validate_requirement(requirement: str) -> str:
    stripped = sanitize_text(requirement).strip()
    if not stripped:
        raise ValueError("Requirement cannot be empty.")
    if len(stripped) > MAX_REQUIREMENT_LENGTH:
        raise ValueError(
            f"Requirement is too long ({len(stripped)} chars). Limit is {MAX_REQUIREMENT_LENGTH}."
        )
    return stripped


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(f"Invalid run id `{run_id}`.")
    return run_id


def bounded_text(value: str, *, limit: int = MAX_DEFECT_TEXT_LENGTH) -> str:
    cleaned = sanitize_text(value).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def sanitize_text(value: str) -> str:
    cleaned = value.lstrip("\ufeff")
    return cleaned.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
