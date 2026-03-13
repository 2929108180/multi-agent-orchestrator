from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

AgentRole = Literal["architect", "frontend", "backend", "reviewer"]
DefectOwner = Literal["frontend", "backend", "shared"]
DefectSeverity = Literal["low", "medium", "high"]
IntegrationDecisionStatus = Literal["auto_accepted", "needs_confirmation", "rejected"]


class WorkerTask(BaseModel):
    role: AgentRole
    objective: str
    deliverables: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    restricted_paths: list[str] = Field(default_factory=list)


class ArchitectPlan(BaseModel):
    summary: str
    shared_contract: list[str] = Field(default_factory=list)
    frontend_task: WorkerTask
    backend_task: WorkerTask
    review_focus: list[str] = Field(default_factory=list)


class AgentExchange(BaseModel):
    role: AgentRole
    model: str
    round_index: int = 0
    prompt: str
    response: str
    proposed_paths: list[str] = Field(default_factory=list)


class ReviewVerdict(BaseModel):
    approved: bool
    summary: str
    findings: list[str] = Field(default_factory=list)
    frontend_action: str = ""
    backend_action: str = ""
    defects: list["ReviewDefect"] = Field(default_factory=list)


class ReviewDefect(BaseModel):
    defect_id: str
    title: str
    owner: DefectOwner
    severity: DefectSeverity
    summary: str
    action: str


class WorkerWorkspaceInfo(BaseModel):
    role: str
    path: str
    git_ref: str
    note_path: str = ""


class WorkflowEvent(BaseModel):
    event_type: str
    role: str = ""
    round_index: int = 0
    message: str = ""
    run_id: str = ""


class IntegrationDecision(BaseModel):
    item_id: str
    role: str
    path: str
    status: IntegrationDecisionStatus
    reason: str
    policy_source: str
    model: str = ""
    diff_path: str = ""
    proposal_path: str = ""


class WorkflowRun(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    requirement: str
    plan: ArchitectPlan
    exchanges: list[AgentExchange] = Field(default_factory=list)
    verdicts: list[ReviewVerdict] = Field(default_factory=list)
    workspaces: list[WorkerWorkspaceInfo] = Field(default_factory=list)
    integration_notes: list[str] = Field(default_factory=list)
    integration_decisions: list[IntegrationDecision] = Field(default_factory=list)
