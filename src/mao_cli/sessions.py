from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from mao_cli.security import bounded_text, sanitize_text, validate_run_id

SessionMode = Literal["mock", "live"]


class SessionTurn(BaseModel):
    turn_id: str = Field(default_factory=lambda: uuid4().hex[:10])
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    user_input: str
    run_id: str = ""
    run_dir: str = ""
    approved: bool | None = None
    summary: str = ""
    defects: list[str] = Field(default_factory=list)


class ChatSessionState(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    config_path: str
    mode: SessionMode
    with_worktrees: bool = False
    turns: list[SessionTurn] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def sessions_root(project_root: Path, runtime_root: str) -> Path:
    root = project_root / runtime_root / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def session_path(project_root: Path, runtime_root: str, session_id: str) -> Path:
    safe_session_id = validate_run_id(session_id)
    return sessions_root(project_root, runtime_root) / f"{safe_session_id}.json"


def create_session(
    *,
    project_root: Path,
    runtime_root: str,
    config_path: Path,
    mode: SessionMode,
    with_worktrees: bool,
) -> ChatSessionState:
    session = ChatSessionState(
        config_path=str(config_path),
        mode=mode,
        with_worktrees=with_worktrees,
    )
    save_session(project_root, runtime_root, session)
    return session


def load_session(project_root: Path, runtime_root: str, session_id: str) -> ChatSessionState:
    path = session_path(project_root, runtime_root, session_id)
    return ChatSessionState.model_validate_json(path.read_text(encoding="utf-8"))


def save_session(project_root: Path, runtime_root: str, session: ChatSessionState) -> Path:
    session.updated_at = datetime.now(UTC)
    path = session_path(project_root, runtime_root, session.session_id)
    path.write_text(json.dumps(session.model_dump(mode="json"), indent=2), encoding="utf-8")
    return path


def list_sessions(project_root: Path, runtime_root: str, limit: int = 10) -> list[ChatSessionState]:
    root = sessions_root(project_root, runtime_root)
    files = sorted(root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return [
        ChatSessionState.model_validate_json(path.read_text(encoding="utf-8"))
        for path in files[:limit]
    ]


def load_latest_session(project_root: Path, runtime_root: str) -> ChatSessionState | None:
    sessions = list_sessions(project_root, runtime_root, limit=1)
    return sessions[0] if sessions else None


def append_turn(
    project_root: Path,
    runtime_root: str,
    session: ChatSessionState,
    *,
    user_input: str,
    run_id: str,
    run_dir: Path,
    approved: bool | None,
    summary: str,
    defects: list[str],
) -> ChatSessionState:
    session.turns.append(
        SessionTurn(
            user_input=sanitize_text(user_input),
            run_id=run_id,
            run_dir=str(run_dir),
            approved=approved,
            summary=sanitize_text(summary),
            defects=[sanitize_text(item) for item in defects],
        )
    )
    save_session(project_root, runtime_root, session)
    return session


def clear_turns(project_root: Path, runtime_root: str, session: ChatSessionState) -> ChatSessionState:
    session.turns = []
    save_session(project_root, runtime_root, session)
    return session


def append_session_note(
    project_root: Path,
    runtime_root: str,
    session_id: str,
    note: str,
) -> Path:
    session = load_session(project_root, runtime_root, session_id)
    session.notes.append(sanitize_text(note))
    return save_session(project_root, runtime_root, session)


def build_conversation_context(session: ChatSessionState, limit: int = 3) -> str:
    turns = session.turns[-limit:]
    if not turns:
        return ""
    lines = ["Conversation context from recent turns:"]
    for index, turn in enumerate(turns, start=1):
        lines.extend(
            [
                f"- Turn {index} request: {bounded_text(turn.user_input, limit=300)}",
                f"  Summary: {bounded_text(turn.summary, limit=300)}",
            ]
        )
        if turn.defects:
            lines.append(f"  Defects: {bounded_text('; '.join(turn.defects), limit=300)}")
    return "\n".join(lines)
