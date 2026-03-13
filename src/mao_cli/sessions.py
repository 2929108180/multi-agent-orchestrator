from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from mao_cli.security import bounded_text, sanitize_text, validate_run_id

SessionMode = Literal["mock", "live"]
ApprovalItemStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "deferred",
    "applied_to_integration",
    "blocked_shared",
]


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
    approval_queue: list["ApprovalQueueItem"] = Field(default_factory=list)
    current_approval_id: str = ""


class ApprovalQueueItem(BaseModel):
    item_id: str
    run_id: str
    role: str
    path: str
    model: str
    status: ApprovalItemStatus
    policy_status: str
    reason: str
    diff_path: str
    proposal_path: str
    merge_candidate_id: str = ""
    shared_file: bool = False


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


def append_approval_items(
    project_root: Path,
    runtime_root: str,
    session: ChatSessionState,
    items: list[ApprovalQueueItem],
) -> ChatSessionState:
    existing_ids = {item.item_id for item in session.approval_queue}
    for item in items:
        if item.item_id not in existing_ids:
            session.approval_queue.append(item)
    if not session.current_approval_id:
        next_item = _next_approval_item(session)
        if next_item:
            session.current_approval_id = next_item.item_id
    save_session(project_root, runtime_root, session)
    return session


def get_queue_item(session: ChatSessionState, item_id: str) -> ApprovalQueueItem | None:
    for item in session.approval_queue:
        if item.item_id == item_id:
            return item
    return None


def update_approval_item(
    project_root: Path,
    runtime_root: str,
    session: ChatSessionState,
    *,
    item_id: str,
    status: ApprovalItemStatus,
) -> ChatSessionState:
    for item in session.approval_queue:
        if item.item_id == item_id:
            item.status = status
            break
    if session.current_approval_id == item_id and status in {"approved", "rejected", "deferred"}:
        session.current_approval_id = ""
    if not session.current_approval_id:
        next_item = _next_approval_item(session)
        if next_item:
            session.current_approval_id = next_item.item_id
    save_session(project_root, runtime_root, session)
    return session


def select_approval_item(
    project_root: Path,
    runtime_root: str,
    session: ChatSessionState,
    item_id: str,
) -> ChatSessionState:
    session.current_approval_id = item_id
    save_session(project_root, runtime_root, session)
    return session


def _next_approval_item(session: ChatSessionState) -> ApprovalQueueItem | None:
    pending = next((item for item in session.approval_queue if item.status == "pending"), None)
    if pending is not None:
        return pending
    return next((item for item in session.approval_queue if item.status == "deferred"), None)


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


def build_task_memory(session: ChatSessionState, role: str, limit: int = 3) -> str:
    turns = session.turns[-limit:]
    if not turns:
        return ""
    lines = [f"Task memory for {role}:"]
    for index, turn in enumerate(turns, start=1):
        lines.extend(
            [
                f"- Recent request {index}: {bounded_text(turn.user_input, limit=220)}",
                f"  Outcome: {bounded_text(turn.summary, limit=220)}",
            ]
        )
        if turn.defects:
            lines.append(f"  Prior review issues: {bounded_text('; '.join(turn.defects), limit=220)}")
    return "\n".join(lines)


def build_review_memory(session: ChatSessionState, limit: int = 3) -> str:
    turns = session.turns[-limit:]
    if not turns:
        return ""
    lines = ["Review memory:"]
    for index, turn in enumerate(turns, start=1):
        lines.extend(
            [
                f"- Reviewed request {index}: {bounded_text(turn.user_input, limit=220)}",
                f"  Previous summary: {bounded_text(turn.summary, limit=220)}",
            ]
        )
        if turn.defects:
            lines.append(f"  Previous defects: {bounded_text('; '.join(turn.defects), limit=220)}")
    return "\n".join(lines)
