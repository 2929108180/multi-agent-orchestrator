from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

from mao_cli.security import sanitize_text


class SkillEntry(BaseModel):
    name: str
    description: str
    path: str


def default_skill_roots(project_root: Path) -> list[Path]:
    home = Path(os.path.expanduser("~"))
    roots = [
        home / ".codex" / "skills",
        project_root / "skills",
    ]
    return [root for root in roots if root.exists()]


def discover_skills(project_root: Path) -> list[SkillEntry]:
    entries: list[SkillEntry] = []
    for root in default_skill_roots(project_root):
        for skill_file in root.rglob("SKILL.md"):
            entries.append(
                SkillEntry(
                    name=skill_file.parent.name,
                    description=_read_skill_description(skill_file),
                    path=str(skill_file),
                )
            )
    entries.sort(key=lambda item: item.name.lower())
    return entries


def read_skill(project_root: Path, skill_name: str) -> SkillEntry:
    target = skill_name.strip().lower()
    for entry in discover_skills(project_root):
        if entry.name.lower() == target:
            return entry
    raise FileNotFoundError(f"Skill `{skill_name}` not found.")


def build_team_context(project_root: Path, limit: int = 5) -> str:
    skills = discover_skills(project_root)
    lines = [
        "Team mode capabilities:",
        "- Roles: architect, frontend, backend, reviewer",
        "- MCP tools: project status, run history, summaries, workflow triggers, session notes",
    ]
    if skills:
        lines.append("- Available skills:")
        for entry in skills[:limit]:
            lines.append(f"  - {entry.name}: {entry.description}")
    return "\n".join(lines)


def append_team_note(project_root: Path, runtime_root: str, note: str, category: str = "general") -> Path:
    team_root = project_root / runtime_root / "team"
    team_root.mkdir(parents=True, exist_ok=True)
    note_path = team_root / f"{category}.md"
    existing = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
    prefix = "\n" if existing else ""
    note_path.write_text(existing + prefix + sanitize_text(note) + "\n", encoding="utf-8")
    return note_path


def _read_skill_description(skill_file: Path) -> str:
    content = skill_file.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in content[:20]:
        stripped = line.strip()
        if stripped.lower().startswith("description:"):
            return sanitize_text(stripped.split(":", 1)[1].strip())
    for line in content:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
            return sanitize_text(stripped)
    return "No description available."
