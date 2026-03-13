from __future__ import annotations

import json
import difflib
from fnmatch import fnmatch
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from mao_cli.config import AppConfig
from mao_cli.core.models import (
    AgentExchange,
    ArchitectPlan,
    IntegrationDecision,
    ReviewDefect,
    ReviewVerdict,
    WorkerTask,
    WorkflowEvent,
    WorkflowRun,
    WorkerWorkspaceInfo,
)
from mao_cli.gitops import WorkerWorkspace, create_worker_worktrees, write_worker_note
from mao_cli.mergeflow import MergeCandidate
from mao_cli.providers import ModelGateway
from mao_cli.security import bounded_text, validate_requirement


def build_architect_plan(requirement: str) -> ArchitectPlan:
    shared_contract = [
        "Define one shared API surface before integration.",
        "Keep frontend route names and backend endpoint names aligned.",
        "Return explicit error states for empty, loading, and failure paths.",
        "Document all request and response fields before implementation.",
    ]
    review_focus = [
        "endpoint naming consistency",
        "request and response field alignment",
        "error handling coverage",
        "missing acceptance criteria",
    ]
    return ArchitectPlan(
        summary=f"Deliver a first working slice for: {requirement}",
        shared_contract=shared_contract,
        frontend_task=WorkerTask(
            role="frontend",
            objective=f"Design the user-facing flow and UI contract for: {requirement}",
            deliverables=[
                "component structure",
                "state flow summary",
                "API consumption contract",
            ],
            acceptance_criteria=[
                "Clearly lists user states",
                "References backend contract fields",
                "Explains loading and error handling",
            ],
            allowed_paths=[
                "frontend/**",
                "ui/**",
                "src/frontend/**",
                "web/**",
            ],
            restricted_paths=[
                "backend/**",
                "api/**",
                "db/**",
                "shared-contracts/**",
            ],
        ),
        backend_task=WorkerTask(
            role="backend",
            objective=f"Design the service, data flow, and API contract for: {requirement}",
            deliverables=[
                "endpoint summary",
                "request response schema outline",
                "validation and error handling notes",
            ],
            acceptance_criteria=[
                "Uses stable endpoint names",
                "Defines request and response fields",
                "Covers validation and error paths",
            ],
            allowed_paths=[
                "backend/**",
                "api/**",
                "db/**",
                "src/backend/**",
            ],
            restricted_paths=[
                "frontend/**",
                "ui/**",
                "web/**",
                "shared-contracts/**",
            ],
        ),
        review_focus=review_focus,
    )


def _render_worker_prompt(plan: ArchitectPlan, task: WorkerTask) -> str:
    return _render_prompt_sections(
        [
            f"Role: {task.role}",
            f"Objective: {task.objective}",
            "Shared contract:",
            *[f"- {item}" for item in plan.shared_contract],
            "Deliverables:",
            *[f"- {item}" for item in task.deliverables],
            "Acceptance criteria:",
            *[f"- {item}" for item in task.acceptance_criteria],
            "Allowed paths:",
            *[f"- {item}" for item in task.allowed_paths],
            "Restricted paths:",
            *[f"- {item}" for item in task.restricted_paths],
            "Do not change files outside your owned paths. Shared contract changes must be escalated to integration.",
            "Respond with a concise but concrete implementation proposal.",
            "At the end, include:",
            "FILE_TARGETS:",
            "- relative/path/example.ext",
        ]
    )


def _render_review_prompt(
    requirement: str,
    plan: ArchitectPlan,
    frontend_response: str,
    backend_response: str,
    conversation_context: str = "",
    team_context: str = "",
    review_memory: str = "",
    capability_context: str = "",
) -> str:
    focus = "\n".join(f"- {item}" for item in plan.review_focus)
    contract = "\n".join(f"- {item}" for item in plan.shared_contract)
    sections = [
        "You are the reviewer.",
        f"Requirement: {requirement}",
    ]
    if conversation_context:
        sections.extend(["Conversation context:", conversation_context])
    if team_context:
        sections.extend(["Team context:", team_context])
    if review_memory:
        sections.extend(["Review memory:", review_memory])
    if capability_context:
        sections.extend(["Capability context:", capability_context])
    sections.extend(
        [
            "Shared contract:",
            contract,
            "Review focus:",
            focus,
            "Frontend response:",
            frontend_response,
            "Backend response:",
            backend_response,
            "Return this exact format:",
            "APPROVED: yes|no",
            "SUMMARY: one line",
            "DEFECT:",
            "ID: stable-defect-id",
            "OWNER: frontend|backend|shared",
            "SEVERITY: low|medium|high",
            "TITLE: short title",
            "SUMMARY: one line description",
            "ACTION: one concrete action",
        ]
    )
    return _render_prompt_sections(sections)


def parse_review_verdict(review_response: str) -> ReviewVerdict:
    approved = False
    summary = ""
    findings: list[str] = []
    frontend_action = ""
    backend_action = ""
    defects: list[ReviewDefect] = []
    defect_fields: dict[str, str] = {}

    mode = ""
    for raw_line in review_response.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line == "DEFECT:":
            _append_defect_from_fields(defects, defect_fields)
            defect_fields = {}
            mode = "defect"
            continue
        if line.startswith("APPROVED:"):
            _append_defect_from_fields(defects, defect_fields)
            defect_fields = {}
            approved = line.split(":", 1)[1].strip().lower() == "yes"
            mode = ""
        elif line.startswith("SUMMARY:"):
            value = bounded_text(line.split(":", 1)[1].strip())
            if mode == "defect":
                defect_fields["summary"] = value
            else:
                summary = value
                mode = ""
        elif line.startswith("FINDINGS:"):
            mode = "findings"
        elif line.startswith("FRONTEND_ACTION:") and not defects:
            frontend_action = line.split(":", 1)[1].strip()
            mode = ""
        elif line.startswith("BACKEND_ACTION:") and not defects:
            backend_action = line.split(":", 1)[1].strip()
            mode = ""
        elif mode == "defect" and ":" in line:
            key, value = line.split(":", 1)
            defect_fields[key.strip().lower()] = bounded_text(value.strip())
        elif mode == "findings" and line.startswith("-"):
            findings.append(bounded_text(line.lstrip("- ").strip()))

    _append_defect_from_fields(defects, defect_fields)

    if not summary:
        summary = "Review completed with unstructured output."

    if defects:
        findings = [defect.summary for defect in defects]
        frontend_action = "; ".join(defect.action for defect in defects if defect.owner in {"frontend", "shared"})
        backend_action = "; ".join(defect.action for defect in defects if defect.owner in {"backend", "shared"})
    elif not defects:
        defects = _legacy_actions_to_defects(frontend_action, backend_action, findings)

    return ReviewVerdict(
        approved=approved,
        summary=summary,
        findings=findings,
        frontend_action=frontend_action,
        backend_action=backend_action,
        defects=defects,
    )


def render_summary(run: WorkflowRun) -> str:
    lines = [
        f"# Run {run.run_id}",
        "",
        "## Requirement",
        run.requirement,
        "",
        "## Architect Summary",
        run.plan.summary,
        "",
        "## Shared Contract",
        *[f"- {item}" for item in run.plan.shared_contract],
        "",
    ]

    if run.workspaces:
        lines.extend(["## Workspaces"])
        lines.extend([f"- {workspace.role}: `{workspace.path}`" for workspace in run.workspaces])
        lines.append("")

    for exchange in run.exchanges:
        lines.extend(
            [
                f"## {exchange.role.title()} Round {exchange.round_index}",
                f"Model: `{exchange.model}`",
                "",
                exchange.response,
                "",
            ]
        )

    for index, verdict in enumerate(run.verdicts, start=1):
        lines.extend(
            [
                f"## Review Round {index}",
                f"Approved: `{verdict.approved}`",
                verdict.summary,
                "",
            ]
        )
        if verdict.defects:
            lines.append("### Defects")
            lines.extend(
                [
                    f"- [{defect.owner}/{defect.severity}] {defect.title}: {defect.action}"
                    for defect in verdict.defects
                ]
            )
            lines.append("")
        if verdict.findings:
            lines.extend([f"- {item}" for item in verdict.findings])
            lines.append("")

    if run.integration_decisions:
        lines.extend(["## Integration Decisions"])
        lines.extend(
            [
                f"- [{decision.status}] {decision.role} -> {decision.path} ({decision.reason})"
                for decision in run.integration_decisions
            ]
        )
        lines.append("")

    return "\n".join(lines)


def persist_run(run: WorkflowRun, output_dir: Path, repository_root: Path) -> Path:
    run_dir = output_dir / run.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps(run.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    (run_dir / "summary.md").write_text(render_summary(run), encoding="utf-8")
    _write_integration_outputs(run, run_dir, repository_root)
    return run_dir


def execute_workflow(
    requirement: str,
    config: AppConfig,
    output_dir: Path,
    repository_root: Path,
    force_mock: bool = False,
    with_worktrees: bool = False,
    event_handler: Callable[[WorkflowEvent], None] | None = None,
    conversation_context: str = "",
    team_context: str = "",
    task_memories: dict[str, str] | None = None,
    review_memory: str = "",
    capability_contexts: dict[str, str] | None = None,
) -> Path:
    requirement = validate_requirement(requirement)
    gateway = ModelGateway(config=config, force_mock=force_mock)
    plan = build_architect_plan(requirement)
    run = WorkflowRun(requirement=requirement, plan=plan)
    _emit_event(event_handler, "workflow_started", run_id=run.run_id, message="workflow started")

    workspace_map: dict[str, WorkerWorkspace] = {}
    if with_worktrees:
        workspace_root = repository_root.parent / f"{repository_root.name}-worktrees"
        created_workspaces = create_worker_worktrees(
            repository_root=repository_root,
            workspace_root=workspace_root,
            run_id=run.run_id,
            roles=["frontend", "backend"],
        )
        workspace_map = {workspace.role: workspace for workspace in created_workspaces}
        run.workspaces = [
            WorkerWorkspaceInfo(
                role=workspace.role,
                path=workspace.path,
                git_ref=workspace.git_ref,
            )
            for workspace in created_workspaces
        ]

    def _call(role: str, prompt: str, round_index: int = 0) -> AgentExchange:
        provider = config.providers[role]
        response = gateway.complete(role=role, prompt=prompt)
        return AgentExchange(
            role=role,
            model=provider.model,
            prompt=prompt,
            response=response,
            round_index=round_index,
            proposed_paths=_extract_proposed_paths(response),
        )

    architect_sections = [
        "You are the architect.",
        f"Requirement: {requirement}",
    ]
    if conversation_context:
        architect_sections.extend(["Conversation context:", conversation_context])
    if team_context:
        architect_sections.extend(["Team context:", team_context])
    architect_sections.append("Summarize the delivery slice and critical interface assumptions.")
    architect_prompt = _render_prompt_sections(architect_sections)
    _emit_event(event_handler, "architect_started", role="architect", run_id=run.run_id, message="planning")
    architect_exchange = _call("architect", architect_prompt)
    run.exchanges.append(architect_exchange)
    _emit_event(event_handler, "architect_completed", role="architect", run_id=run.run_id, message="plan ready")

    frontend_prompt = _render_worker_prompt(plan, plan.frontend_task)
    backend_prompt = _render_worker_prompt(plan, plan.backend_task)
    frontend_task_memory = (task_memories or {}).get("frontend", "")
    backend_task_memory = (task_memories or {}).get("backend", "")
    frontend_capability_context = (capability_contexts or {}).get("frontend", "")
    backend_capability_context = (capability_contexts or {}).get("backend", "")
    reviewer_capability_context = (capability_contexts or {}).get("reviewer", "")
    if conversation_context or team_context or frontend_task_memory or frontend_capability_context:
        context_sections: list[str] = []
        if conversation_context:
            context_sections.extend(["Conversation context:", conversation_context])
        if team_context:
            context_sections.extend(["Team context:", team_context])
        if frontend_task_memory:
            context_sections.extend(["Task memory:", frontend_task_memory])
        if frontend_capability_context:
            context_sections.extend(["Capability context:", frontend_capability_context])
        context_block = _render_prompt_sections(context_sections)
        frontend_prompt = frontend_prompt + "\n\n" + context_block
    if conversation_context or team_context or backend_task_memory or backend_capability_context:
        context_sections = []
        if conversation_context:
            context_sections.extend(["Conversation context:", conversation_context])
        if team_context:
            context_sections.extend(["Team context:", team_context])
        if backend_task_memory:
            context_sections.extend(["Task memory:", backend_task_memory])
        if backend_capability_context:
            context_sections.extend(["Capability context:", backend_capability_context])
        backend_prompt = backend_prompt + "\n\n" + _render_prompt_sections(context_sections)
    _emit_event(event_handler, "frontend_started", role="frontend", run_id=run.run_id, message="running")
    _emit_event(event_handler, "backend_started", role="backend", run_id=run.run_id, message="running")
    with ThreadPoolExecutor(max_workers=2) as executor:
        frontend_future = executor.submit(_call, "frontend", frontend_prompt, 0)
        backend_future = executor.submit(_call, "backend", backend_prompt, 0)
        frontend_exchange = frontend_future.result()
        backend_exchange = backend_future.result()

    run.exchanges.extend([frontend_exchange, backend_exchange])
    _emit_event(event_handler, "frontend_completed", role="frontend", run_id=run.run_id, message="completed")
    _emit_event(event_handler, "backend_completed", role="backend", run_id=run.run_id, message="completed")
    _write_workspace_notes(run, workspace_map, frontend_exchange, backend_exchange)

    review_prompt = _render_review_prompt(
        requirement=requirement,
        plan=plan,
        frontend_response=frontend_exchange.response,
        backend_response=backend_exchange.response,
        conversation_context=conversation_context,
        team_context=team_context,
        review_memory=review_memory,
        capability_context=reviewer_capability_context,
    )
    _emit_event(event_handler, "review_started", role="reviewer", run_id=run.run_id, message="checking")
    review_exchange = _call("reviewer", review_prompt, 0)
    run.exchanges.append(review_exchange)
    verdict = parse_review_verdict(review_exchange.response)
    ownership_defects, integration_notes = _evaluate_ownership(
        config=config,
        frontend_task=plan.frontend_task,
        backend_task=plan.backend_task,
        frontend_exchange=frontend_exchange,
        backend_exchange=backend_exchange,
    )
    run.integration_notes.extend(integration_notes)
    verdict = _merge_enforcement_defects(verdict, ownership_defects)
    run.integration_decisions = _build_integration_decisions(
        config=config,
        frontend_exchange=frontend_exchange,
        backend_exchange=backend_exchange,
        ownership_defects=ownership_defects,
    )
    run.verdicts.append(verdict)
    _emit_event(
        event_handler,
        "review_completed",
        role="reviewer",
        run_id=run.run_id,
        message="approved" if verdict.approved else "defects found",
    )

    repair_round = 0
    current_frontend_exchange = frontend_exchange
    current_backend_exchange = backend_exchange
    while not verdict.approved and repair_round < config.workflow.max_repair_rounds:
        defects_by_owner = _group_defects_by_owner(verdict.defects)
        frontend_defects = defects_by_owner["frontend"] + defects_by_owner["shared"]
        backend_defects = defects_by_owner["backend"] + defects_by_owner["shared"]
        if not frontend_defects and not backend_defects:
            break

        repair_round += 1
        _emit_event(
            event_handler,
            "repair_round_started",
            run_id=run.run_id,
            round_index=repair_round,
            message=f"repair round {repair_round}",
        )
        frontend_repair_prompt = _render_repair_prompt(frontend_prompt, frontend_defects)
        backend_repair_prompt = _render_repair_prompt(backend_prompt, backend_defects)
        with ThreadPoolExecutor(max_workers=2) as executor:
            if frontend_defects:
                _emit_event(
                    event_handler,
                    "repair_target_started",
                    role="frontend",
                    run_id=run.run_id,
                    round_index=repair_round,
                    message="repairing",
                )
            if backend_defects:
                _emit_event(
                    event_handler,
                    "repair_target_started",
                    role="backend",
                    run_id=run.run_id,
                    round_index=repair_round,
                    message="repairing",
                )
            frontend_future = (
                executor.submit(_call, "frontend", frontend_repair_prompt, repair_round)
                if frontend_defects
                else None
            )
            backend_future = (
                executor.submit(_call, "backend", backend_repair_prompt, repair_round)
                if backend_defects
                else None
            )
            if frontend_future is not None:
                current_frontend_exchange = frontend_future.result()
                run.exchanges.append(current_frontend_exchange)
                _emit_event(
                    event_handler,
                    "repair_target_completed",
                    role="frontend",
                    run_id=run.run_id,
                    round_index=repair_round,
                    message="repaired",
                )
            if backend_future is not None:
                current_backend_exchange = backend_future.result()
                run.exchanges.append(current_backend_exchange)
                _emit_event(
                    event_handler,
                    "repair_target_completed",
                    role="backend",
                    run_id=run.run_id,
                    round_index=repair_round,
                    message="repaired",
                )

        _write_workspace_notes(run, workspace_map, current_frontend_exchange, current_backend_exchange)
        review_prompt = _render_review_prompt(
            requirement=requirement,
            plan=plan,
            frontend_response=current_frontend_exchange.response,
            backend_response=current_backend_exchange.response,
            conversation_context=conversation_context,
            team_context=team_context,
            review_memory=review_memory,
            capability_context=reviewer_capability_context,
        )
        _emit_event(
            event_handler,
            "review_started",
            role="reviewer",
            run_id=run.run_id,
            round_index=repair_round,
            message="checking",
        )
        review_exchange = _call("reviewer", review_prompt, repair_round)
        run.exchanges.append(review_exchange)
        verdict = parse_review_verdict(review_exchange.response)
        ownership_defects, integration_notes = _evaluate_ownership(
            config=config,
            frontend_task=plan.frontend_task,
            backend_task=plan.backend_task,
            frontend_exchange=current_frontend_exchange,
            backend_exchange=current_backend_exchange,
        )
        run.integration_notes.extend(note for note in integration_notes if note not in run.integration_notes)
        verdict = _merge_enforcement_defects(verdict, ownership_defects)
        run.integration_decisions = _build_integration_decisions(
            config=config,
            frontend_exchange=current_frontend_exchange,
            backend_exchange=current_backend_exchange,
            ownership_defects=ownership_defects,
        )
        run.verdicts.append(verdict)
        _emit_event(
            event_handler,
            "review_completed",
            role="reviewer",
            run_id=run.run_id,
            round_index=repair_round,
            message="approved" if verdict.approved else "defects found",
        )

    run_dir = persist_run(run, output_dir, repository_root)
    _emit_event(event_handler, "workflow_completed", run_id=run.run_id, message="workflow completed")
    return run_dir


def _write_workspace_notes(
    run: WorkflowRun,
    workspace_map: dict[str, WorkerWorkspace],
    frontend_exchange: AgentExchange,
    backend_exchange: AgentExchange,
) -> None:
    if not workspace_map:
        return

    for exchange in (frontend_exchange, backend_exchange):
        workspace = workspace_map.get(exchange.role)
        if workspace is None:
            continue
        note_path = write_worker_note(
            workspace=workspace,
            content="\n".join(
                [
                    f"# {exchange.role.title()} Notes",
                    "",
                    f"Round: {exchange.round_index}",
                    "",
                    exchange.response,
                ]
            ),
        )
        for workspace_info in run.workspaces:
            if workspace_info.role == exchange.role:
                workspace_info.note_path = str(note_path)


def _append_defect_from_fields(defects: list[ReviewDefect], fields: dict[str, str]) -> None:
    if not fields:
        return
    defect_id = bounded_text(fields.get("id", "unspecified-defect"), limit=100)
    title = bounded_text(fields.get("title", "Untitled defect"), limit=160)
    owner = fields.get("owner", "shared").lower()
    if owner not in {"frontend", "backend", "shared"}:
        owner = "shared"
    severity = fields.get("severity", "medium").lower()
    if severity not in {"low", "medium", "high"}:
        severity = "medium"
    summary = bounded_text(fields.get("summary", "No summary provided."))
    action = bounded_text(fields.get("action", "Review and align the implementation."))
    defects.append(
        ReviewDefect(
            defect_id=defect_id,
            title=title,
            owner=owner,  # type: ignore[arg-type]
            severity=severity,  # type: ignore[arg-type]
            summary=summary,
            action=action,
        )
    )


def _legacy_actions_to_defects(
    frontend_action: str,
    backend_action: str,
    findings: list[str],
) -> list[ReviewDefect]:
    defects: list[ReviewDefect] = []
    if frontend_action and frontend_action.upper() != "NONE":
        defects.append(
            ReviewDefect(
                defect_id="legacy-frontend-action",
                title="Frontend follow-up required",
                owner="frontend",
                severity="high",
                summary=bounded_text(findings[0] if findings else frontend_action),
                action=bounded_text(frontend_action),
            )
        )
    if backend_action and backend_action.upper() != "NONE":
        defects.append(
            ReviewDefect(
                defect_id="legacy-backend-action",
                title="Backend follow-up required",
                owner="backend",
                severity="high",
                summary=bounded_text(findings[0] if findings else backend_action),
                action=bounded_text(backend_action),
            )
        )
    return defects


def _group_defects_by_owner(defects: list[ReviewDefect]) -> dict[str, list[ReviewDefect]]:
    grouped: dict[str, list[ReviewDefect]] = {
        "frontend": [],
        "backend": [],
        "shared": [],
    }
    for defect in defects:
        grouped[defect.owner].append(defect)
    return grouped


def _render_repair_prompt(task_prompt: str, defects: list[ReviewDefect]) -> str:
    defect_lines = []
    for defect in defects:
        defect_lines.extend(
            [
                "DEFECT:",
                f"ID: {defect.defect_id}",
                f"OWNER: {defect.owner}",
                f"SEVERITY: {defect.severity}",
                f"TITLE: {defect.title}",
                f"SUMMARY: {defect.summary}",
                f"ACTION: {defect.action}",
            ]
        )
    return _render_prompt_sections(
        [
            task_prompt,
            "",
            "Reviewer defects assigned to you:",
            *defect_lines,
            "Revise your proposal and keep it consistent with the shared contract.",
        ]
    )


def _render_prompt_sections(parts: list[str]) -> str:
    return "\n".join(part for part in parts if part)


def _extract_proposed_paths(response: str) -> list[str]:
    paths: list[str] = []
    capture = False
    for raw_line in response.splitlines():
        line = raw_line.strip()
        if line == "FILE_TARGETS:":
            capture = True
            continue
        if capture and line.startswith("-"):
            candidate = line.lstrip("- ").strip()
            if candidate:
                paths.append(candidate)
            continue
        if capture and line and not line.startswith("-"):
            break
    return paths


def _evaluate_ownership(
    *,
    config: AppConfig,
    frontend_task: WorkerTask,
    backend_task: WorkerTask,
    frontend_exchange: AgentExchange,
    backend_exchange: AgentExchange,
) -> tuple[list[ReviewDefect], list[str]]:
    defects: list[ReviewDefect] = []
    notes: list[str] = []
    shared_prefixes = ("shared-contracts/", "contracts/", "schemas/", "shared/")

    for task, exchange in ((frontend_task, frontend_exchange), (backend_task, backend_exchange)):
        for path in exchange.proposed_paths:
            normalized = path.replace("\\", "/")
            if any(fnmatch(normalized, pattern) for pattern in task.restricted_paths):
                defects.append(
                    ReviewDefect(
                        defect_id=f"ownership-{exchange.role}-{normalized}",
                        title="Ownership violation",
                        owner=exchange.role,
                        severity="high",
                        summary=f"{exchange.role} proposed a restricted path: {normalized}",
                        action="Remove the restricted path and stay inside owned files only.",
                    )
                )
            if any(normalized.startswith(prefix) for prefix in shared_prefixes):
                notes.append(f"Shared path requires integration layer: {normalized}")
                defects.append(
                    ReviewDefect(
                        defect_id=f"integration-{normalized}",
                        title="Integration layer required",
                        owner="shared",
                        severity="high",
                        summary=f"Shared path `{normalized}` must go through integration, not a worker directly.",
                        action="Escalate this file to integration instead of assigning it to frontend or backend.",
                    )
                )

    overlaps = set(frontend_exchange.proposed_paths).intersection(set(backend_exchange.proposed_paths))
    for path in overlaps:
        normalized = path.replace("\\", "/")
        notes.append(f"Conflict detected between frontend and backend on: {normalized}")
        defects.append(
            ReviewDefect(
                defect_id=f"conflict-{normalized}",
                title="Cross-worker file conflict",
                owner="shared",
                severity="high",
                summary=f"Both frontend and backend proposed the same file: {normalized}",
                action="Reject direct worker writes and route this file through integration.",
            )
        )
    return defects, notes


def _build_integration_decisions(
    *,
    config: AppConfig,
    frontend_exchange: AgentExchange,
    backend_exchange: AgentExchange,
    ownership_defects: list[ReviewDefect],
) -> list[IntegrationDecision]:
    decisions: list[IntegrationDecision] = []
    defect_lookup = {defect.summary: defect for defect in ownership_defects}
    shared_paths = {
        defect.summary.split("`")[1]
        for defect in ownership_defects
        if defect.title == "Integration layer required" and "`" in defect.summary
    }
    conflict_paths = {
        defect.summary.rsplit(": ", 1)[-1]
        for defect in ownership_defects
        if defect.title == "Cross-worker file conflict"
    }
    rejected_paths = {
        defect.summary.rsplit(": ", 1)[-1]
        for defect in ownership_defects
        if defect.title == "Ownership violation"
    }

    for exchange in (frontend_exchange, backend_exchange):
        base_mode, policy_source = config.approval.resolve_mode(role=exchange.role, model=exchange.model)
        for path in exchange.proposed_paths:
            normalized = path.replace("\\", "/")
            if normalized in conflict_paths:
                decisions.append(
                    IntegrationDecision(
                        item_id=f"{exchange.role}:{normalized}",
                        role=exchange.role,
                        path=normalized,
                        status=_status_from_mode(config.approval.conflict_mode),
                        reason="conflict between workers",
                        policy_source="conflict_mode",
                        model=exchange.model,
                    )
                )
                continue
            if normalized in shared_paths:
                decisions.append(
                    IntegrationDecision(
                        item_id=f"{exchange.role}:{normalized}",
                        role=exchange.role,
                        path=normalized,
                        status=_status_from_mode(config.approval.shared_path_mode),
                        reason="shared path must go through integration",
                        policy_source="shared_path_mode",
                        model=exchange.model,
                        shared_file=True,
                    )
                )
                continue
            if normalized in rejected_paths:
                decisions.append(
                    IntegrationDecision(
                        item_id=f"{exchange.role}:{normalized}",
                    role=exchange.role,
                    path=normalized,
                    status="rejected",
                        reason="path violates worker ownership rules",
                    policy_source="ownership",
                    model=exchange.model,
                    shared_file=False,
                )
            )
            continue
        decisions.append(
            IntegrationDecision(
                    item_id=f"{exchange.role}:{normalized}",
                    role=exchange.role,
                    path=normalized,
                    status=_status_from_mode(base_mode),
                reason="clean worker-owned path",
                policy_source=policy_source,
                model=exchange.model,
                shared_file=False,
            )
        )
    return decisions


def _status_from_mode(mode: str) -> str:
    if mode == "auto":
        return "auto_accepted"
    if mode == "reject":
        return "rejected"
    return "needs_confirmation"


def _merge_enforcement_defects(verdict: ReviewVerdict, extra_defects: list[ReviewDefect]) -> ReviewVerdict:
    if not extra_defects:
        return verdict
    existing_ids = {defect.defect_id for defect in verdict.defects}
    merged = verdict.defects[:]
    for defect in extra_defects:
        if defect.defect_id not in existing_ids:
            merged.append(defect)
    verdict.defects = merged
    verdict.findings = [defect.summary for defect in merged]
    verdict.frontend_action = "; ".join(
        defect.action for defect in merged if defect.owner in {"frontend", "shared"}
    )
    verdict.backend_action = "; ".join(
        defect.action for defect in merged if defect.owner in {"backend", "shared"}
    )
    if any(defect.severity == "high" for defect in merged):
        verdict.approved = False
    return verdict


def _emit_event(
    event_handler: Callable[[WorkflowEvent], None] | None,
    event_type: str,
    *,
    role: str = "",
    round_index: int = 0,
    message: str = "",
    run_id: str = "",
) -> None:
    if event_handler is None:
        return
    event_handler(
        WorkflowEvent(
            event_type=event_type,
            role=role,
            round_index=round_index,
            message=message,
            run_id=run_id,
        )
    )


def _write_integration_outputs(run: WorkflowRun, run_dir: Path, repository_root: Path) -> None:
    latest_exchange_by_role = _latest_exchange_by_role(run)
    diffs_root = run_dir / "diffs"
    proposals_root = run_dir / "proposals"
    diffs_root.mkdir(parents=True, exist_ok=True)
    proposals_root.mkdir(parents=True, exist_ok=True)

    for decision in run.integration_decisions:
        exchange = latest_exchange_by_role.get(decision.role)
        proposed_content = _build_proposed_content(decision, exchange)
        proposal_path = proposals_root / decision.role / decision.path
        proposal_path.parent.mkdir(parents=True, exist_ok=True)
        proposal_path.write_text(proposed_content, encoding="utf-8")
        decision.proposal_path = str(proposal_path)

        base_path = repository_root / decision.path
        base_lines = (
            base_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if base_path.exists()
            else []
        )
        proposed_lines = proposed_content.splitlines()
        diff_text = "\n".join(
            difflib.unified_diff(
                base_lines,
                proposed_lines,
                fromfile=str(base_path),
                tofile=str(proposal_path),
                lineterm="",
            )
        )
        diff_file = diffs_root / f"{decision.role}-{_safe_diff_name(decision.path)}.diff"
        diff_file.write_text(diff_text, encoding="utf-8")
        decision.diff_path = str(diff_file)

    integration_payload = {
        "notes": run.integration_notes,
        "decisions": [decision.model_dump() for decision in run.integration_decisions],
    }
    (run_dir / "integration.json").write_text(
        json.dumps(integration_payload, indent=2),
        encoding="utf-8",
    )
    lines = ["# Integration Decisions", ""]
    if run.integration_notes:
        lines.append("## Notes")
        lines.extend(f"- {note}" for note in run.integration_notes)
        lines.append("")
    if run.integration_decisions:
        lines.append("## Decisions")
        lines.extend(
            f"- [{decision.status}] {decision.role} -> {decision.path} ({decision.policy_source})"
            for decision in run.integration_decisions
        )
        lines.append("")
    (run_dir / "integration.md").write_text("\n".join(lines), encoding="utf-8")
    _write_merge_candidate_outputs(run, run_dir)


def _latest_exchange_by_role(run: WorkflowRun) -> dict[str, AgentExchange]:
    latest: dict[str, AgentExchange] = {}
    for exchange in run.exchanges:
        latest[exchange.role] = exchange
    return latest


def _build_proposed_content(decision: IntegrationDecision, exchange: AgentExchange | None) -> str:
    return exchange.response if exchange is not None else "No worker response available."


def _safe_diff_name(path: str) -> str:
    return path.replace("\\", "_").replace("/", "_").replace(":", "_")


def _write_merge_candidate_outputs(run: WorkflowRun, run_dir: Path) -> None:
    candidates = [
        MergeCandidate(
            run_id=run.run_id,
            item_id=decision.item_id,
            role=decision.role,
            path=decision.path,
            model=decision.model,
            integration_workspace="",
            applied_path="",
            shared_file=decision.shared_file,
            status=(
                "blocked_shared"
                if decision.shared_file
                else ("ready_for_merge" if decision.status == "auto_accepted" else decision.status)
            ),
            reason=decision.reason,
        )
        for decision in run.integration_decisions
    ]
    (run_dir / "merge_candidates.json").write_text(
        json.dumps([candidate.model_dump(mode="json") for candidate in candidates], indent=2),
        encoding="utf-8",
    )
    lines = ["# Merge Candidates", ""]
    for candidate in candidates:
        lines.append(
            f"- [{candidate.status}] {candidate.role} -> {candidate.path} shared={candidate.shared_file}"
        )
    lines.append("")
    (run_dir / "merge_candidates.md").write_text("\n".join(lines), encoding="utf-8")
