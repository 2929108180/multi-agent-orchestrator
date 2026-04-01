from __future__ import annotations

import json
import difflib
from fnmatch import fnmatch
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from mao_cli.config import AppConfig
from mao_cli.core.models import (
    AgentExchange,
    ArchitectPlan,
    IntegrationDecision,
    IntegrationBinding,
    IntegrationReport,
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
from mao_cli.tool_runtime import run_with_tools


ROLE_BRIEFS_PROTOCOL_V1 = [
    "ROLE_BRIEFS:",
    "FRONTEND: ...",
    "BACKEND: ...",
    "INTEGRATION: ...",
    "REVIEWER: ...",
    "END_ROLE_BRIEFS",
]


INTEGRATION_PROTOCOL_V1 = [
    "INTEGRATION_REPORT:",
    "ROUND: <int>",
    "STATUS: ok|needs_changes",
    "SUMMARY: one line",
    "",
    "KEY_FINDINGS:",
    "- ...",
    "",
    "BINDING:",
    "ID: stable-binding-id",
    "FRONTEND: ...",
    "BACKEND: ...",
    "REQUEST_FIELDS: a,b,c",
    "RESPONSE_FIELDS: x,y,z",
    "MATCH: yes|no",
    "NOTES: ...",
    "",
    "ISSUE:",
    "ID: stable-issue-id",
    "OWNER: frontend|backend|shared",
    "SEVERITY: low|medium|high",
    "TITLE: ...",
    "SUMMARY: ...",
    "ACTION: ...",
    "",
    "OPEN_QUESTIONS:",
    "- ...",
    "",
    "FILE_TARGETS:",
    "- relative/path.ext",
]


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
        "frontend and backend contract binding quality",
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
        integration_task=WorkerTask(
            role="integration",
            objective=f"Bind the frontend and backend contract for: {requirement}",
            deliverables=[
                "api binding summary",
                "shared contract glue notes",
                "integration candidate file targets",
            ],
            acceptance_criteria=[
                "Maps frontend calls to backend endpoints",
                "Explains shared request and response fields",
                "Flags shared files that must go through integration",
            ],
            allowed_paths=[
                "shared-contracts/**",
                "contracts/**",
                "schemas/**",
                "shared/**",
                "integration/**",
            ],
            restricted_paths=[
                "frontend/**",
                "backend/**",
            ],
            response_protocol=INTEGRATION_PROTOCOL_V1,
        ),
        review_focus=review_focus,
    )


def _render_worker_prompt(plan: ArchitectPlan, task: WorkerTask, *, role_brief: str = "") -> str:
    sections: list[str] = [
        f"Role: {task.role}",
        f"Objective: {task.objective}",
        "",
        "# Thinking Rules (CRITICAL — follow BEFORE producing any output)",
        "",
        "## Phase 1: Deep Understanding",
        "- What is the user/architect's REAL intent? (not just literal words)",
        "- What would a COMPLETE, HIGH-QUALITY result look like?",
        "- If the objective references a known concept (poem, protocol, algorithm, pattern),",
        "  I must produce the FULL, CORRECT, CANONICAL version — never a stub or fragment.",
        "",
        "## Phase 2: Context & Dependencies",
        "- How does my output connect to what other roles produce?",
        "- What existing code/patterns in this project must I be consistent with?",
        "- If I'm modifying code: what calls this? what imports this? what breaks if I change this?",
        "- If I have file-access tools: READ the target file BEFORE proposing changes.",
        "  Understand imports, structure, style. Never propose changes to code I haven't seen.",
        "",
        "## Phase 3: Complete Delivery",
        "- Deliver COMPLETE results. No placeholders, no 'rest stays the same', no TODOs.",
        "- If implementing a feature: full implementation with all edge cases.",
        "- If writing content: every line, not a summary.",
        "- If modifying multiple files: address ALL of them.",
        "",
        "## Phase 4: Self-Check",
        "- Does my output fulfill the REAL intent?",
        "- Is it complete? correct? consistent with the codebase?",
        "- Did I miss any dependent/related changes?",
        "",
    ]
    if role_brief:
        sections.extend(["Role brief (from architect):", role_brief])
    sections.extend(
        [
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
        ]
    )

    if task.response_protocol:
        sections.extend(["Return this exact format:", *task.response_protocol])
    else:
        sections.extend(
            [
                "At the end, include:",
                "FILE_TARGETS:",
                "- relative/path/example.ext",
            ]
        )

    return _render_prompt_sections(sections)


def _render_review_prompt(
    requirement: str,
    plan: ArchitectPlan,
    integration_report: str,
    frontend_response: str,
    backend_response: str,
    conversation_context: str = "",
    team_context: str = "",
    review_memory: str = "",
    capability_context: str = "",
    reviewer_brief: str = "",
    reviewer_role_memory: str = "",
) -> str:
    focus = "\n".join(f"- {item}" for item in plan.review_focus)
    contract = "\n".join(f"- {item}" for item in plan.shared_contract)
    sections = [
        "You are the reviewer — a thorough, intelligent quality gate who thinks deeply.",
        "",
        "# Review Thinking Rules (CRITICAL)",
        "",
        "## Intent Alignment (most important)",
        "- First, understand what the user ACTUALLY wanted — not just the literal request.",
        "- '改为春晓' means the COMPLETE poem must appear, not just a title or fragment.",
        "- '加个功能' means a FULLY working feature, not a stub.",
        "- If the output only partially addresses the real intent → DEFECT.",
        "",
        "## Completeness Check",
        "- Is the output COMPLETE? No missing pieces, no TODOs, no placeholders?",
        "- Does it cover all affected files, not just the primary one?",
        "- If code was modified, were callers/importers/tests also updated?",
        "",
        "## Correctness Check",
        "- Is the content accurate? (poems, algorithms, protocols must be canonical)",
        "- Is the code syntactically and logically correct?",
        "- Are imports, types, and interfaces consistent?",
        "",
        "## Context Fit",
        "- Does the output match the existing codebase style and patterns?",
        "- Were established conventions respected?",
        "- If you have file-access tools, use them to verify against the actual codebase.",
        "",
        f"Requirement: {requirement}",
    ]
    if reviewer_brief:
        sections.extend(["Reviewer brief (from architect):", reviewer_brief])
    if conversation_context:
        sections.extend(["Conversation context:", conversation_context])
    if team_context:
        sections.extend(["Team context:", team_context])
    if review_memory:
        sections.extend(["Review memory:", review_memory])
    if reviewer_role_memory:
        sections.extend(["Role memory:", reviewer_role_memory])
    if capability_context:
        sections.extend(["Capability context:", capability_context])
    sections.extend(
        [
            "Shared contract:",
            contract,
            "Review focus:",
            focus,
            "Integration report (PRIMARY):",
            integration_report,
            "Frontend response (REFERENCE):",
            frontend_response,
            "Backend response (REFERENCE):",
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


def _normalize_csv_fields(value: str) -> list[str]:
    stripped = value.strip()
    if not stripped:
        return []
    return [item.strip() for item in stripped.split(",") if item.strip()]


def parse_integration_report(
    integration_response: str,
    *,
    round_index: int = 0,
    model: str = "",
) -> IntegrationReport | None:
    raw = bounded_text(integration_response, limit=8000)
    if not raw.strip():
        return None

    status: str = "ok"
    summary: str = ""
    key_findings: list[str] = []
    bindings: list[IntegrationBinding] = []
    issues: list[ReviewDefect] = []
    open_questions: list[str] = []

    mode = ""
    current_binding: dict[str, str] = {}
    current_issue: dict[str, str] = {}

    def flush_binding() -> None:
        nonlocal current_binding
        if not current_binding:
            return
        binding_id = current_binding.get("id") or f"binding-{len(bindings)+1}"
        match_value = (current_binding.get("match") or "").strip().lower()
        bindings.append(
            IntegrationBinding(
                binding_id=binding_id,
                frontend=current_binding.get("frontend", ""),
                backend=current_binding.get("backend", ""),
                request_fields=_normalize_csv_fields(current_binding.get("request_fields", "")),
                response_fields=_normalize_csv_fields(current_binding.get("response_fields", "")),
                match=match_value in {"yes", "true", "1"},
                notes=current_binding.get("notes", ""),
            )
        )
        current_binding = {}

    def flush_issue() -> None:
        nonlocal current_issue
        if not current_issue:
            return
        defect_id = current_issue.get("id") or f"integration-issue-{len(issues)+1}"
        owner = (current_issue.get("owner") or "shared").strip().lower()
        if owner not in {"frontend", "backend", "shared"}:
            owner = "shared"
        severity = (current_issue.get("severity") or "medium").strip().lower()
        if severity not in {"low", "medium", "high"}:
            severity = "medium"
        issues.append(
            ReviewDefect(
                defect_id=defect_id,
                owner=owner,  # type: ignore[arg-type]
                severity=severity,  # type: ignore[arg-type]
                title=current_issue.get("title") or "Integration issue",
                summary=current_issue.get("summary") or "",
                action=current_issue.get("action") or "",
            )
        )
        current_issue = {}

    saw_header = False
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line == "INTEGRATION_REPORT:":
            saw_header = True
            mode = ""
            continue

        if not saw_header:
            continue

        if line == "FILE_TARGETS:":
            flush_binding()
            flush_issue()
            break

        if line == "BINDING:":
            flush_binding()
            flush_issue()
            mode = "binding"
            continue

        if line == "ISSUE:":
            flush_binding()
            flush_issue()
            mode = "issue"
            continue

        if line == "KEY_FINDINGS:":
            flush_binding()
            flush_issue()
            mode = "key_findings"
            continue

        if line == "OPEN_QUESTIONS:":
            flush_binding()
            flush_issue()
            mode = "open_questions"
            continue

        if line.startswith("ROUND:"):
            # trust the orchestrator-provided round_index for storage; accept model value as informational only.
            mode = ""
            continue

        if line.startswith("STATUS:"):
            value = line.split(":", 1)[1].strip().lower()
            if value in {"ok", "needs_changes"}:
                status = value
            mode = ""
            continue

        if line.startswith("SUMMARY:") and mode != "issue":
            summary = bounded_text(line.split(":", 1)[1].strip())
            mode = ""
            continue

        if mode in {"key_findings", "open_questions"} and line.startswith("-"):
            item = bounded_text(line.lstrip("- ").strip())
            if mode == "key_findings":
                key_findings.append(item)
            else:
                open_questions.append(item)
            continue

        if mode in {"binding", "issue"} and ":" in line:
            key, value = line.split(":", 1)
            normalized_key = key.strip().lower()
            normalized_value = bounded_text(value.strip())
            if mode == "binding":
                current_binding[normalized_key] = normalized_value
            else:
                current_issue[normalized_key] = normalized_value
            continue

    flush_binding()
    flush_issue()

    if not summary:
        summary = "Integration completed with unstructured output."

    return IntegrationReport(
        round_index=round_index,
        status=status,  # type: ignore[arg-type]
        summary=summary,
        key_findings=key_findings,
        bindings=bindings,
        issues=issues,
        open_questions=open_questions,
        raw_text=raw,
        model=model,
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
    role_memories: dict[str, str] | None = None,
    review_memory: str = "",
    capability_contexts: dict[str, str] | None = None,
    enabled_roles: set[str] | None = None,
) -> Path:
    requirement = validate_requirement(requirement)
    gateway = ModelGateway(config=config, force_mock=force_mock)
    active_roles = enabled_roles or set(config.providers.keys())
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
        response, _tool_trace = run_with_tools(
            gateway=gateway,
            role=role,
            base_prompt=prompt,
            project_root=repository_root,
            runtime_root=config.runtime_root,
            config=config,
            event_handler=event_handler,
            run_id=run.run_id,
            round_index=round_index,
        )
        return AgentExchange(
            role=role,
            model=provider.model,
            prompt=prompt,
            response=response,
            round_index=round_index,
            proposed_paths=_extract_proposed_paths(response),
        )

    architect_sections = [
        "You are the architect — the strategic thinker, planner, and technical leader.",
        "You think deeply about what the user REALLY wants and design a plan that delivers it COMPLETELY.",
        "",
        "# Thinking Rules (CRITICAL)",
        "",
        "## Intent Analysis",
        "- The user's literal text is a STARTING POINT, not the full specification.",
        "- Ask: what does the user actually want to achieve? What would make them say 'perfect'?",
        "- '改一下登录页' → comprehensive login page redesign, not a one-line tweak.",
        "- '加个搜索功能' → fully working search with UI, backend, edge cases.",
        "- When something is referenced by name, the team must produce it COMPLETELY and CORRECTLY.",
        "",
        "## Context Awareness",
        "- If you have file-access tools, USE THEM to understand the existing codebase before planning.",
        "- Consider: what code already exists? what patterns are used? what will the change affect?",
        "- Your plan must account for ALL files and dependencies that need changes — not just the obvious ones.",
        "",
        "## Complete Planning",
        "- Every worker must receive enough context to deliver a COMPLETE result.",
        "- Don't leave ambiguity for workers to resolve — resolve it here.",
        "- If the requirement is complex, break it into clear, concrete sub-tasks.",
        "- Think about: dependencies between changes, edge cases, integration points.",
        "",
        f"Requirement: {requirement}",
    ]
    if conversation_context:
        architect_sections.extend(["Conversation context:", conversation_context])
    if team_context:
        architect_sections.extend(["Team context:", team_context])
    architect_sections.append("Summarize the delivery slice and critical interface assumptions.")
    architect_prompt = _render_prompt_sections(architect_sections)
    _emit_event(event_handler, "architect_started", role="architect", run_id=run.run_id, message="planning")
    _emit_event(
        event_handler,
        "architect_dispatched",
        role="architect",
        run_id=run.run_id,
        message=f"task={_summarize_text('Summarize the delivery slice and critical interface assumptions.')}",
    )
    architect_exchange = _call("architect", architect_prompt)
    run.exchanges.append(architect_exchange)
    _emit_event(
        event_handler,
        "architect_completed",
        role="architect",
        run_id=run.run_id,
        message=_summarize_text(architect_exchange.response),
    )

    briefs_prompt = _render_prompt_sections(
        [
            "You are the architect.",
            "Generate role-specific briefs for the team members.",
            "IMPORTANT: Each brief must convey the FULL intent of the requirement — not just the literal words.",
            "If the user asked for something by name (a poem, a protocol, an algorithm), explicitly tell the worker to produce the COMPLETE canonical version.",
            "Only output the ROLE_BRIEFS block. No other text.",
            "",
            f"Requirement: {requirement}",
            "",
            "ROLE_BRIEFS:",
            "FRONTEND: <one paragraph; concrete tasks and constraints>",
            "BACKEND: <one paragraph; concrete tasks and constraints>",
            "INTEGRATION: <one paragraph; contract/binding focus>",
            "REVIEWER: <one paragraph; review focus and risks>",
            "END_ROLE_BRIEFS",
        ]
    )
    _emit_event(
        event_handler,
        "architect_dispatched",
        role="architect",
        run_id=run.run_id,
        message=f"task={_summarize_text('Generate role briefs for distribution.')}",
    )
    briefs_exchange = _call("architect", briefs_prompt)
    run.exchanges.append(briefs_exchange)
    role_briefs = _parse_role_briefs(briefs_exchange.response)

    frontend_prompt = _render_worker_prompt(plan, plan.frontend_task, role_brief=role_briefs.get("frontend", ""))
    backend_prompt = _render_worker_prompt(plan, plan.backend_task, role_brief=role_briefs.get("backend", ""))
    integration_prompt = _render_worker_prompt(plan, plan.integration_task, role_brief=role_briefs.get("integration", ""))
    frontend_task_memory = (task_memories or {}).get("frontend", "")
    backend_task_memory = (task_memories or {}).get("backend", "")
    frontend_role_memory = (role_memories or {}).get("frontend", "")
    backend_role_memory = (role_memories or {}).get("backend", "")
    integration_role_memory = (role_memories or {}).get("integration", "")
    reviewer_role_memory = (role_memories or {}).get("reviewer", "")

    frontend_capability_context = (capability_contexts or {}).get("frontend", "")
    backend_capability_context = (capability_contexts or {}).get("backend", "")
    reviewer_capability_context = (capability_contexts or {}).get("reviewer", "")

    if (
        conversation_context
        or team_context
        or frontend_task_memory
        or frontend_role_memory
        or frontend_capability_context
    ):
        context_sections: list[str] = []
        if conversation_context:
            context_sections.extend(["Conversation context:", conversation_context])
        if team_context:
            context_sections.extend(["Team context:", team_context])
        if frontend_task_memory:
            context_sections.extend(["Task memory:", frontend_task_memory])
        if frontend_role_memory:
            context_sections.extend(["Role memory:", frontend_role_memory])
        if frontend_capability_context:
            context_sections.extend(["Capability context:", frontend_capability_context])
        context_block = _render_prompt_sections(context_sections)
        frontend_prompt = frontend_prompt + "\n\n" + context_block

    if (
        conversation_context
        or team_context
        or backend_task_memory
        or backend_role_memory
        or backend_capability_context
    ):
        context_sections = []
        if conversation_context:
            context_sections.extend(["Conversation context:", conversation_context])
        if team_context:
            context_sections.extend(["Team context:", team_context])
        if backend_task_memory:
            context_sections.extend(["Task memory:", backend_task_memory])
        if backend_role_memory:
            context_sections.extend(["Role memory:", backend_role_memory])
        if backend_capability_context:
            context_sections.extend(["Capability context:", backend_capability_context])
        backend_prompt = backend_prompt + "\n\n" + _render_prompt_sections(context_sections)

    integration_capability_context = (capability_contexts or {}).get("integration", "")
    if conversation_context or team_context or integration_role_memory or integration_capability_context:
        context_sections = []
        if conversation_context:
            context_sections.extend(["Conversation context:", conversation_context])
        if team_context:
            context_sections.extend(["Team context:", team_context])
        if integration_role_memory:
            context_sections.extend(["Role memory:", integration_role_memory])
        if integration_capability_context:
            context_sections.extend(["Capability context:", integration_capability_context])
        integration_prompt = integration_prompt + "\n\n" + _render_prompt_sections(context_sections)
    frontend_exchange = AgentExchange(role="frontend", model=config.providers["frontend"].model, prompt="", response="", round_index=0)
    backend_exchange = AgentExchange(role="backend", model=config.providers["backend"].model, prompt="", response="", round_index=0)
    integration_exchange = AgentExchange(role="integration", model=config.providers["integration"].model, prompt="", response="", round_index=0)
    futures: dict = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        if "frontend" in active_roles:
            _emit_event(
                event_handler,
                "frontend_started",
                role="frontend",
                run_id=run.run_id,
                message=f"calling frontend... objective={_summarize_text(plan.frontend_task.objective)}",
                model=config.providers["frontend"].model,
            )
            futures[executor.submit(_call, "frontend", frontend_prompt, 0)] = "frontend"
        if "backend" in active_roles:
            _emit_event(
                event_handler,
                "backend_started",
                role="backend",
                run_id=run.run_id,
                message=f"calling backend... objective={_summarize_text(plan.backend_task.objective)}",
                model=config.providers["backend"].model,
            )
            futures[executor.submit(_call, "backend", backend_prompt, 0)] = "backend"
        for future in as_completed(futures):
            role = futures[future]
            exchange = future.result()
            if role == "frontend":
                frontend_exchange = exchange
                _emit_event(
                    event_handler,
                    "frontend_completed",
                    role="frontend",
                    run_id=run.run_id,
                    message=_summarize_text(frontend_exchange.response),
                    model=frontend_exchange.model,
                )
            else:
                backend_exchange = exchange
                _emit_event(
                    event_handler,
                    "backend_completed",
                    role="backend",
                    run_id=run.run_id,
                    message=_summarize_text(backend_exchange.response),
                    model=backend_exchange.model,
                )

    run.exchanges.extend([frontend_exchange, backend_exchange])
    _write_workspace_notes(run, workspace_map, frontend_exchange, backend_exchange)

    integration_exchange = None
    if "integration" in active_roles:
        _emit_event(
            event_handler,
            "integration_started",
            role="integration",
            run_id=run.run_id,
            round_index=0,
            message=f"calling integration... objective={_summarize_text(plan.integration_task.objective)}",
            model=config.providers["integration"].model,
        )
        integration_context = _render_prompt_sections(
            [
                "Frontend response:",
                frontend_exchange.response,
                "Backend response:",
                backend_exchange.response,
                "Shared contract:",
                "\n".join(f"- {item}" for item in plan.shared_contract),
            ]
        )
        integration_exchange = _call("integration", integration_prompt + "\n\n" + integration_context, 0)
        run.exchanges.append(integration_exchange)
        _emit_event(
            event_handler,
            "integration_completed",
            role="integration",
            run_id=run.run_id,
            round_index=0,
            message=_summarize_text(integration_exchange.response),
            model=integration_exchange.model,
        )

    integration_report_text = integration_exchange.response if integration_exchange else ""
    parsed_integration_report = parse_integration_report(
        integration_report_text,
        round_index=0,
        model=integration_exchange.model if integration_exchange else "",
    )
    if parsed_integration_report is not None:
        run.integration_reports.append(parsed_integration_report)

    # Reviewer still sees the full requirement (not summarized).
    review_prompt = _render_review_prompt(
        requirement=requirement,
        plan=plan,
        integration_report=integration_report_text,
        frontend_response=frontend_exchange.response,
        backend_response=backend_exchange.response,
        conversation_context=conversation_context,
        team_context=team_context,
        review_memory=review_memory,
        capability_context=reviewer_capability_context,
        reviewer_brief=role_briefs.get("reviewer", ""),
        reviewer_role_memory=reviewer_role_memory,
    )
    if "reviewer" in active_roles:
        _emit_event(
            event_handler,
            "review_started",
            role="reviewer",
            run_id=run.run_id,
            message=f"calling reviewer... focus={_summarize_text(', '.join(plan.review_focus))}",
            model=config.providers["reviewer"].model,
        )
        review_exchange = _call("reviewer", review_prompt, 0)
        run.exchanges.append(review_exchange)
        verdict = parse_review_verdict(review_exchange.response)
    else:
        review_exchange = AgentExchange(role="reviewer", model=config.providers["reviewer"].model, prompt="", response="Reviewer disabled.", round_index=0)
        verdict = ReviewVerdict(approved=True, summary="Reviewer disabled.", findings=[], defects=[])
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
        model=config.providers["reviewer"].model,
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
        if "integration" in active_roles:
            _emit_event(
                event_handler,
                "integration_started",
                role="integration",
                run_id=run.run_id,
                round_index=repair_round,
                message=f"calling integration... objective={_summarize_text(plan.integration_task.objective)}",
                model=config.providers["integration"].model,
            )
            integration_context = _render_prompt_sections(
                [
                    "Frontend response:",
                    current_frontend_exchange.response,
                    "Backend response:",
                    current_backend_exchange.response,
                    "Shared contract:",
                    "\n".join(f"- {item}" for item in plan.shared_contract),
                ]
            )
            integration_exchange = _call(
                "integration",
                integration_prompt + "\n\n" + integration_context,
                repair_round,
            )
            run.exchanges.append(integration_exchange)
            _emit_event(
                event_handler,
                "integration_completed",
                role="integration",
                run_id=run.run_id,
                round_index=repair_round,
                message=_summarize_text(integration_exchange.response),
                model=integration_exchange.model,
            )
        else:
            integration_exchange = None

        integration_report_text = integration_exchange.response if integration_exchange else ""
        parsed_integration_report = parse_integration_report(
            integration_report_text,
            round_index=repair_round,
            model=integration_exchange.model if integration_exchange else "",
        )
        if parsed_integration_report is not None:
            run.integration_reports.append(parsed_integration_report)

        review_prompt = _render_review_prompt(
            requirement=requirement,
            plan=plan,
            integration_report=integration_report_text,
            frontend_response=current_frontend_exchange.response,
            backend_response=current_backend_exchange.response,
            conversation_context=conversation_context,
            team_context=team_context,
            review_memory=review_memory,
            capability_context=reviewer_capability_context,
            reviewer_brief=role_briefs.get("reviewer", ""),
            reviewer_role_memory=reviewer_role_memory,
        )
        _emit_event(
            event_handler,
            "review_started",
            role="reviewer",
            run_id=run.run_id,
            round_index=repair_round,
            message="calling reviewer...",
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
    recap = (
        f"architect={_summarize_text(architect_exchange.response)} | "
        f"frontend={_summarize_text(current_frontend_exchange.response)} | "
        f"backend={_summarize_text(current_backend_exchange.response)} | "
        f"reviewer={_summarize_text(verdict.summary)}"
    )
    _emit_event(event_handler, "workflow_recap", run_id=run.run_id, message=recap)
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


def _parse_role_briefs(text: str) -> dict[str, str]:
    """Parse a ROLE_BRIEFS block.

    Returns lowercase keys: frontend/backend/integration/reviewer.
    """

    lines = text.splitlines()
    start = None
    end = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "ROLE_BRIEFS:":
            start = idx + 1
            continue
        if stripped == "END_ROLE_BRIEFS":
            end = idx
            break

    if start is None or end is None or end < start:
        return {}

    briefs: dict[str, str] = {}
    for raw in lines[start:end]:
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        k = key.strip().lower()
        if k in {"frontend", "backend", "integration", "reviewer"}:
            briefs[k] = bounded_text(value.strip(), limit=1200)
    return briefs


def _summarize_text(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


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
    model: str = "",
    metadata: dict[str, str] | None = None,
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
            model=model,
            metadata=metadata or {},
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
        "reports": [report.model_dump() for report in run.integration_reports],
    }
    (run_dir / "integration.json").write_text(
        json.dumps(integration_payload, indent=2),
        encoding="utf-8",
    )
    lines = ["# Integration Decisions", ""]
    if run.integration_reports:
        lines.append("## Integration Reports")
        for report in run.integration_reports:
            lines.append(f"- Round {report.round_index}: [{report.status}] {report.summary}")
        lines.append("")
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
