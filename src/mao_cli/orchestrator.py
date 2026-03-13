from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mao_cli.config import AppConfig
from mao_cli.core.models import (
    AgentExchange,
    ArchitectPlan,
    ReviewDefect,
    ReviewVerdict,
    WorkerTask,
    WorkflowRun,
    WorkerWorkspaceInfo,
)
from mao_cli.gitops import WorkerWorkspace, create_worker_worktrees, write_worker_note
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
        ),
        review_focus=review_focus,
    )


def _render_worker_prompt(plan: ArchitectPlan, task: WorkerTask) -> str:
    return "\n".join(
        [
            f"Role: {task.role}",
            f"Objective: {task.objective}",
            "Shared contract:",
            *[f"- {item}" for item in plan.shared_contract],
            "Deliverables:",
            *[f"- {item}" for item in task.deliverables],
            "Acceptance criteria:",
            *[f"- {item}" for item in task.acceptance_criteria],
            "Respond with a concise but concrete implementation proposal.",
        ]
    )


def _render_review_prompt(
    requirement: str,
    plan: ArchitectPlan,
    frontend_response: str,
    backend_response: str,
) -> str:
    focus = "\n".join(f"- {item}" for item in plan.review_focus)
    contract = "\n".join(f"- {item}" for item in plan.shared_contract)
    return "\n".join(
        [
            "You are the reviewer.",
            f"Requirement: {requirement}",
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

    return "\n".join(lines)


def persist_run(run: WorkflowRun, output_dir: Path) -> Path:
    run_dir = output_dir / run.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps(run.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    (run_dir / "summary.md").write_text(render_summary(run), encoding="utf-8")
    return run_dir


def execute_workflow(
    requirement: str,
    config: AppConfig,
    output_dir: Path,
    repository_root: Path,
    force_mock: bool = False,
    with_worktrees: bool = False,
) -> Path:
    requirement = validate_requirement(requirement)
    gateway = ModelGateway(config=config, force_mock=force_mock)
    plan = build_architect_plan(requirement)
    run = WorkflowRun(requirement=requirement, plan=plan)

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
            role=role, model=provider.model, prompt=prompt, response=response, round_index=round_index
        )

    architect_prompt = "\n".join(
        [
            "You are the architect.",
            f"Requirement: {requirement}",
            "Summarize the delivery slice and critical interface assumptions.",
        ]
    )
    run.exchanges.append(_call("architect", architect_prompt))

    frontend_prompt = _render_worker_prompt(plan, plan.frontend_task)
    backend_prompt = _render_worker_prompt(plan, plan.backend_task)
    with ThreadPoolExecutor(max_workers=2) as executor:
        frontend_future = executor.submit(_call, "frontend", frontend_prompt, 0)
        backend_future = executor.submit(_call, "backend", backend_prompt, 0)
        frontend_exchange = frontend_future.result()
        backend_exchange = backend_future.result()

    run.exchanges.extend([frontend_exchange, backend_exchange])
    _write_workspace_notes(run, workspace_map, frontend_exchange, backend_exchange)

    review_prompt = _render_review_prompt(
        requirement=requirement,
        plan=plan,
        frontend_response=frontend_exchange.response,
        backend_response=backend_exchange.response,
    )
    review_exchange = _call("reviewer", review_prompt, 0)
    run.exchanges.append(review_exchange)
    verdict = parse_review_verdict(review_exchange.response)
    run.verdicts.append(verdict)

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
        frontend_repair_prompt = _render_repair_prompt(frontend_prompt, frontend_defects)
        backend_repair_prompt = _render_repair_prompt(backend_prompt, backend_defects)
        with ThreadPoolExecutor(max_workers=2) as executor:
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
            if backend_future is not None:
                current_backend_exchange = backend_future.result()
                run.exchanges.append(current_backend_exchange)

        _write_workspace_notes(run, workspace_map, current_frontend_exchange, current_backend_exchange)
        review_prompt = _render_review_prompt(
            requirement=requirement,
            plan=plan,
            frontend_response=current_frontend_exchange.response,
            backend_response=current_backend_exchange.response,
        )
        review_exchange = _call("reviewer", review_prompt, repair_round)
        run.exchanges.append(review_exchange)
        verdict = parse_review_verdict(review_exchange.response)
        run.verdicts.append(verdict)

    return persist_run(run, output_dir)


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
    return "\n".join(
        [
            task_prompt,
            "",
            "Reviewer defects assigned to you:",
            *defect_lines,
            "Revise your proposal and keep it consistent with the shared contract.",
        ]
    )
