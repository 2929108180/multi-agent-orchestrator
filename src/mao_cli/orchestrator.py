from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mao_cli.config import AppConfig
from mao_cli.core.models import (
    AgentExchange,
    ArchitectPlan,
    ReviewVerdict,
    WorkerTask,
    WorkflowRun,
)
from mao_cli.providers import ModelGateway


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
            "FINDINGS:",
            "- finding 1",
            "FRONTEND_ACTION: action or NONE",
            "BACKEND_ACTION: action or NONE",
        ]
    )


def parse_review_verdict(review_response: str) -> ReviewVerdict:
    approved = False
    summary = ""
    findings: list[str] = []
    frontend_action = ""
    backend_action = ""

    mode = ""
    for raw_line in review_response.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("APPROVED:"):
            approved = line.split(":", 1)[1].strip().lower() == "yes"
            mode = ""
        elif line.startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip()
            mode = ""
        elif line.startswith("FINDINGS:"):
            mode = "findings"
        elif line.startswith("FRONTEND_ACTION:"):
            frontend_action = line.split(":", 1)[1].strip()
            mode = ""
        elif line.startswith("BACKEND_ACTION:"):
            backend_action = line.split(":", 1)[1].strip()
            mode = ""
        elif mode == "findings" and line.startswith("-"):
            findings.append(line.lstrip("- ").strip())

    if not summary:
        summary = "Review completed with unstructured output."

    return ReviewVerdict(
        approved=approved,
        summary=summary,
        findings=findings,
        frontend_action=frontend_action,
        backend_action=backend_action,
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
    force_mock: bool = False,
) -> Path:
    gateway = ModelGateway(config=config, force_mock=force_mock)
    plan = build_architect_plan(requirement)
    run = WorkflowRun(requirement=requirement, plan=plan)

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
    while not verdict.approved and repair_round < config.workflow.max_repair_rounds:
        repair_round += 1
        frontend_repair_prompt = "\n".join(
            [
                frontend_prompt,
                "",
                f"Reviewer feedback: {verdict.frontend_action}",
                "Revise your proposal and keep it consistent with the shared contract.",
            ]
        )
        backend_repair_prompt = "\n".join(
            [
                backend_prompt,
                "",
                f"Reviewer feedback: {verdict.backend_action}",
                "Revise your proposal and keep it consistent with the shared contract.",
            ]
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            frontend_future = executor.submit(_call, "frontend", frontend_repair_prompt, repair_round)
            backend_future = executor.submit(_call, "backend", backend_repair_prompt, repair_round)
            frontend_exchange = frontend_future.result()
            backend_exchange = backend_future.result()

        run.exchanges.extend([frontend_exchange, backend_exchange])
        review_prompt = _render_review_prompt(
            requirement=requirement,
            plan=plan,
            frontend_response=frontend_exchange.response,
            backend_response=backend_exchange.response,
        )
        review_exchange = _call("reviewer", review_prompt, repair_round)
        run.exchanges.append(review_exchange)
        verdict = parse_review_verdict(review_exchange.response)
        run.verdicts.append(verdict)

    return persist_run(run, output_dir)
