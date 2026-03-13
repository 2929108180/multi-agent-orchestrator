from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from mao_cli.config import AppConfig, load_config
from mao_cli.core.models import WorkflowEvent
from mao_cli.gitops import WorkerWorkspace, apply_proposal_to_workspace, ensure_named_worktree
from mao_cli.orchestrator import execute_workflow
from mao_cli.providers import inspect_providers
from mao_cli.registry import registered_or_discovered_skills
from mao_cli.security import validate_requirement
from mao_cli.sessions import (
    ApprovalQueueItem,
    ChatSessionState,
    append_approval_items,
    append_turn,
    build_conversation_context,
    build_review_memory,
    build_task_memory,
    clear_turns,
    create_session,
    get_queue_item,
    load_latest_session,
    load_session,
    list_sessions,
    select_approval_item,
    update_approval_item,
)
from mao_cli.terminal import create_table

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import CompleteEvent, Completer, Completion
    from prompt_toolkit.document import Document
except ImportError:  # pragma: no cover - fallback when optional dependency is unavailable
    PromptSession = None
    CompleteEvent = object
    Document = object

    class Completer:  # type: ignore[no-redef]
        pass

    class Completion:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            pass

CHAT_COMMANDS = {
    "/help": "Show built-in commands and how chat mode works.",
    "/status": "Show the current chat session settings.",
    "/doctor": "Show provider readiness for this chat session.",
    "/mode": "Show whether the session is using mock or live providers.",
    "/history": "Show the saved turns for this session.",
    "/context": "Show the conversation context sent into new runs.",
    "/clear": "Clear the saved turns in the current session.",
    "/skills": "List available local skills for team mode.",
    "/resume": "Choose and resume a saved session from this chat window.",
    "/queue": "List queued approval items.",
    "/review": "Show the currently selected approval item.",
    "/pick": "Open a specific approval item by queue number.",
    "/approve": "Approve the currently selected queued change.",
    "/reject": "Reject the currently selected queued change.",
    "/defer": "Pause the current approval item and come back later.",
    "/last": "Show the latest run directory from this session.",
    "/exit": "Exit the chat session.",
    "/quit": "Exit the chat session.",
}

CHAT_BANNER_LINES = [
    r" __  __    _    ___  ",
    r"|  \/  |  / \  / _ \ ",
    r"| |\/| | / _ \| | | |",
    r"| |  | |/ ___ \ |_| |",
    r"|_|  |_/_/   \_\___/ ",
]


class SlashCommandCompleter(Completer):
    def get_completions(self, document: Document, complete_event: CompleteEvent):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        lowered = text.lower()
        for command, description in CHAT_COMMANDS.items():
            if command.startswith(lowered):
                yield Completion(
                    command,
                    start_position=-len(text),
                    display=command,
                    display_meta=description,
                )


class ChatSession:
    def __init__(
        self,
        *,
        project_root: Path,
        config_path: Path,
        output_dir: Path | None,
        mock: bool,
        with_worktrees: bool,
        session_id: str | None,
        resume_latest: bool,
        console: Console,
    ) -> None:
        self.project_root = project_root
        self.config_path = config_path
        self.config = load_config(config_path)
        self.output_dir = output_dir or (project_root / self.config.artifacts_root / "runs")
        self.mock = mock
        self.with_worktrees = with_worktrees
        self.console = console
        self.last_run_dir: Path | None = None
        self.prompt_session = None
        self.skills = registered_or_discovered_skills(project_root, self.config.runtime_root)
        self.team_context = self._build_team_context()
        self.session = self._load_or_create_session(session_id=session_id, resume_latest=resume_latest)
        self.last_run_dir = self._derive_last_run_dir()
        self.current_integration_workspace: WorkerWorkspace | None = None
        self._preflight_live_mode()

    def print_welcome(self) -> None:
        self.console.print(self._build_banner())
        self.console.print("[bold white]Multi-Agent Orchestrator chat[/bold white]")
        self.console.print("[cyan]Type a requirement to run the workflow.[/cyan]")
        self.console.print(
            f"[white]session={self.session.session_id}[/white] "
            f"[green]mode={'mock' if self.mock else 'live'}[/green] "
            f"[magenta]skills={len(self.skills)}[/magenta]"
        )
        if self._interactive_completion_available():
            self.console.print("[green]Type `/` to see commands. Use `Tab` to complete slash commands.[/green]")
        else:
            self.console.print(
                "[yellow]Type `/help` for commands. Tab completion is unavailable until `prompt_toolkit` is installed.[/yellow]"
            )
        self.console.print(
            "[magenta]Built-in commands:[/magenta] /help /status /doctor /mode /history /context /skills /resume /queue /review /approve /reject /defer /last /exit"
        )

    def run(self) -> None:
        self.print_welcome()
        while True:
            try:
                raw = self._prompt()
            except EOFError:
                self.console.print("Chat closed.")
                return
            except KeyboardInterrupt:
                self.console.print("\nChat interrupted.")
                return

            line = raw.strip()
            if not line:
                continue
            if line.startswith("/"):
                if self._handle_command(line):
                    return
                continue

            self._run_requirement(line)

    def _prompt(self) -> str:
        if not self._interactive_completion_available():
            return input("mao> ")
        if self.prompt_session is None:
            self.prompt_session = self._create_prompt_session()
        if self.prompt_session is None:
            return input("mao> ")
        return self.prompt_session.prompt(
            "mao> ",
            complete_while_typing=True,
            bottom_toolbar=self._bottom_toolbar,
        )

    def _bottom_toolbar(self) -> str:
        if self.prompt_session is None:
            return "Enter a requirement, or use /help for commands."
        current = self.prompt_session.default_buffer.document.text.strip().lower()
        if current in CHAT_COMMANDS:
            return CHAT_COMMANDS[current]
        if current.startswith("/"):
            matches = [cmd for cmd in CHAT_COMMANDS if cmd.startswith(current)]
            if matches:
                return " | ".join(f"{cmd}: {CHAT_COMMANDS[cmd]}" for cmd in matches[:3])
        return "Enter a requirement, or type `/` and press Tab for commands."

    def _handle_command(self, line: str) -> bool:
        command, argument = self._parse_command(line.lower())
        if command in {"/exit", "/quit"}:
            self.console.print("Chat closed.")
            return True
        if command == "/help":
            table = create_table("Chat Commands")
            table.add_column("Command")
            table.add_column("Purpose")
            for name, purpose in CHAT_COMMANDS.items():
                table.add_row(name, purpose)
            self.console.print("Enter a product or coding requirement to run one workflow.")
            self.console.print(table)
            return False
        if command == "/status":
            self.console.print(
                "\n".join(
                    [
                        f"session_id={self.session.session_id}",
                        f"config={self.config_path}",
                        f"mock={self.mock}",
                        f"with_worktrees={self.with_worktrees}",
                        f"output_dir={self.output_dir}",
                        f"last_run={self.last_run_dir or '-'}",
                        f"turns={len(self.session.turns)}",
                    ]
                )
            )
            return False
        if command == "/mode":
            self.console.print(f"mode={'mock' if self.mock else 'live'}")
            return False
        if command == "/doctor":
            rows = inspect_providers(self.config, force_mock=self.mock)
            for row in rows:
                self.console.print(
                    f"[{row.role}] adapter={row.adapter} model={row.model} ready={row.ready} note={row.note}"
                )
            return False
        if command == "/history":
            self._print_history()
            return False
        if command == "/context":
            context = build_conversation_context(self.session)
            self.console.print(context or "No conversation context yet.")
            return False
        if command == "/clear":
            self.session = clear_turns(self.project_root, self.config.runtime_root, self.session)
            self.last_run_dir = None
            self.console.print("Session turns cleared.")
            return False
        if command == "/skills":
            self._print_skills()
            return False
        if command == "/resume":
            self._resume_session()
            return False
        if command == "/queue":
            self._print_queue()
            return False
        if command == "/review":
            self._show_selected_approval()
            return False
        if command == "/pick":
            self._pick_approval(argument)
            return False
        if command == "/approve":
            self._update_selected_approval("approved")
            return False
        if command == "/reject":
            self._update_selected_approval("rejected")
            return False
        if command == "/defer":
            self._update_selected_approval("deferred")
            return False
        if command == "/last":
            if self.last_run_dir is None:
                self.console.print("No run has been executed in this chat session yet.")
                return False
            self.console.print(f"last_run={self.last_run_dir}")
            return False

        self.console.print(f"Unknown command: {line}. Use /help.")
        return False

    def _run_requirement(self, requirement: str) -> None:
        try:
            requirement = validate_requirement(requirement)
        except ValueError as exc:
            self.console.print(f"Invalid requirement: {exc}")
            return

        self.console.print("Running workflow...")
        conversation_context = build_conversation_context(self.session)
        task_memories = {
            "frontend": build_task_memory(self.session, "frontend"),
            "backend": build_task_memory(self.session, "backend"),
        }
        review_memory = build_review_memory(self.session)
        run_dir = execute_workflow(
            requirement=requirement,
            config=self.config,
            output_dir=self.output_dir,
            repository_root=self.project_root,
            force_mock=self.mock,
            with_worktrees=self.with_worktrees,
            event_handler=self._handle_workflow_event,
            conversation_context=conversation_context,
            team_context=self.team_context,
            task_memories=task_memories,
            review_memory=review_memory,
        )
        self.last_run_dir = run_dir

        payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        verdicts = payload.get("verdicts") or []
        approved = verdicts[-1].get("approved") if verdicts else None
        summary = verdicts[-1].get("summary") if verdicts else "No verdict summary."
        defects = [defect.get("summary", "") for defect in verdicts[-1].get("defects", [])] if verdicts else []
        self.session = append_turn(
            self.project_root,
            self.config.runtime_root,
            self.session,
            user_input=requirement,
            run_id=payload.get("run_id", ""),
            run_dir=run_dir,
            approved=approved,
            summary=summary,
            defects=defects,
        )
        self._append_run_approval_items(run_dir)

        self.console.print(f"Run artifacts saved to: {run_dir}")
        self.console.print(f"approved={approved}")
        self.console.print(f"summary={summary}")
        pending = [item for item in self.session.approval_queue if item.status in {"pending", "deferred"}]
        if pending:
            self.console.print(f"approval_queue={len(pending)} pending items. Use /queue or /review.")

    def _interactive_completion_available(self) -> bool:
        return PromptSession is not None and sys.stdin.isatty() and sys.stdout.isatty()

    def _create_prompt_session(self):
        if PromptSession is None:
            return None
        try:
            return PromptSession(completer=SlashCommandCompleter())
        except Exception:
            return None

    def _handle_workflow_event(self, event: WorkflowEvent) -> None:
        line = self._format_event(event)
        if line:
            self.console.print(line)

    def _format_event(self, event: WorkflowEvent) -> str:
        role = event.role or "workflow"
        if event.event_type == "workflow_started":
            return "workflow: started"
        if event.event_type == "architect_started":
            return "architect: planning"
        if event.event_type == "architect_completed":
            return "architect: completed"
        if event.event_type == "frontend_started":
            return "frontend: running"
        if event.event_type == "backend_started":
            return "backend: running"
        if event.event_type == "frontend_completed":
            return "frontend: completed"
        if event.event_type == "backend_completed":
            return "backend: completed"
        if event.event_type == "review_started":
            return "reviewer: checking"
        if event.event_type == "review_completed":
            return f"reviewer: {event.message}"
        if event.event_type == "repair_round_started":
            return f"repair round {event.round_index}"
        if event.event_type == "repair_target_started":
            return f"{role}: repairing"
        if event.event_type == "repair_target_completed":
            return f"{role}: repaired"
        if event.event_type == "workflow_completed":
            return "workflow: completed"
        return ""

    def _resolve_command(self, command: str) -> str:
        base = command.split(" ", 1)[0]
        if base in CHAT_COMMANDS:
            return base
        matches = [name for name in CHAT_COMMANDS if name.startswith(base)]
        if len(matches) == 1:
            return matches[0]
        return base

    def _parse_command(self, line: str) -> tuple[str, str]:
        base = self._resolve_command(line)
        parts = line.split(" ", 1)
        argument = parts[1].strip() if len(parts) > 1 else ""
        return base, argument

    def _build_banner(self) -> Panel:
        banner = Text()
        styles = ["bold cyan", "bold bright_blue", "bold bright_magenta", "bold bright_red", "bold yellow"]
        for index, line in enumerate(CHAT_BANNER_LINES):
            banner.append(line, style=styles[index % len(styles)])
            banner.append("\n")
        banner.append("Cross-vendor coding agents, one local cockpit.", style="bold white")
        return Panel(
            banner,
            border_style="bright_blue",
            title="[bold cyan]MAO[/bold cyan]",
            subtitle="[bold magenta]chat[/bold magenta]",
            padding=(1, 2),
        )

    def _build_team_context(self) -> str:
        lines = [
            "Team mode capabilities:",
            "- Roles: architect, frontend, backend, reviewer",
            "- MCP tools: project status, run history, summaries, workflow triggers, session notes",
        ]
        if self.skills:
            lines.append("- Available skills:")
            for entry in self.skills[:5]:
                lines.append(f"  - {entry.name}: {entry.description}")
        return "\n".join(lines)

    def _load_or_create_session(self, *, session_id: str | None, resume_latest: bool) -> ChatSessionState:
        if session_id:
            return load_session(self.project_root, self.config.runtime_root, session_id)
        if resume_latest:
            latest = load_latest_session(self.project_root, self.config.runtime_root)
            if latest is not None:
                return latest
        return create_session(
            project_root=self.project_root,
            runtime_root=self.config.runtime_root,
            config_path=self.config_path,
            mode="mock" if self.mock else "live",
            with_worktrees=self.with_worktrees,
        )

    def _preflight_live_mode(self) -> None:
        if self.mock:
            return
        rows = inspect_providers(self.config, force_mock=False)
        not_ready = [row for row in rows if not row.ready]
        if not_ready:
            message = "; ".join(f"{row.role}: {row.note}" for row in not_ready)
            raise RuntimeError(f"Live mode preflight failed. {message}")

    def _print_history(self) -> None:
        if not self.session.turns:
            self.console.print("No saved turns in this session yet.")
            return
        table = create_table("Session History")
        table.add_column("Turn")
        table.add_column("Approved")
        table.add_column("Summary")
        for turn in self.session.turns[-10:]:
            table.add_row(turn.turn_id, str(turn.approved), turn.summary)
        self.console.print(table)

    def _print_skills(self) -> None:
        if not self.skills:
            self.console.print("No local skills discovered.")
            return
        table = create_table("Available Skills")
        table.add_column("Name")
        table.add_column("Description")
        for skill in self.skills[:20]:
            table.add_row(skill.name, skill.description)
        self.console.print(table)

    def _append_run_approval_items(self, run_dir: Path) -> None:
        integration_path = run_dir / "integration.json"
        if not integration_path.exists():
            return
        payload = json.loads(integration_path.read_text(encoding="utf-8"))
        run_id = run_dir.name
        queue_items: list[ApprovalQueueItem] = []
        for decision in payload.get("decisions", []):
            status = "approved" if decision["status"] == "auto_accepted" else (
                "rejected" if decision["status"] == "rejected" else "pending"
            )
            queue_items.append(
                ApprovalQueueItem(
                    item_id=f"{run_id}:{decision['item_id']}",
                    run_id=run_id,
                    role=decision["role"],
                    path=decision["path"],
                    model=decision.get("model", ""),
                    status=status,
                    policy_status=decision["status"],
                    reason=decision["reason"],
                    diff_path=decision.get("diff_path", ""),
                    proposal_path=decision.get("proposal_path", ""),
                )
            )
        self.session = append_approval_items(
            self.project_root,
            self.config.runtime_root,
            self.session,
            queue_items,
        )

    def _print_queue(self) -> None:
        if not self.session.approval_queue:
            self.console.print("No approval items queued.")
            return
        table = create_table("Approval Queue")
        table.add_column("No.")
        table.add_column("Status")
        table.add_column("Role")
        table.add_column("Path")
        table.add_column("Reason")
        for index, item in enumerate(self.session.approval_queue, start=1):
            marker = "*" if item.item_id == self.session.current_approval_id else ""
            table.add_row(str(index), f"{item.status}{marker}", item.role, item.path, item.reason)
        self.console.print(table)

    def _show_selected_approval(self) -> None:
        if not self.session.current_approval_id:
            self.console.print("No approval item is currently selected.")
            return
        item = get_queue_item(self.session, self.session.current_approval_id)
        if item is None:
            self.console.print("Selected approval item was not found.")
            return
        self._print_approval_item(item)
        self._prompt_review_choice(item)

    def _pick_approval(self, argument: str) -> None:
        if not argument.isdigit():
            self.console.print("Use `/pick <number>` to open one approval item.")
            return
        index = int(argument)
        if index < 1 or index > len(self.session.approval_queue):
            self.console.print("Approval item number is out of range.")
            return
        item = self.session.approval_queue[index - 1]
        self.session = select_approval_item(
            self.project_root,
            self.config.runtime_root,
            self.session,
            item.item_id,
        )
        self._print_approval_item(item)
        self._prompt_review_choice(item)

    def _update_selected_approval(self, status: str) -> None:
        if not self.session.current_approval_id:
            self.console.print("No approval item is currently selected.")
            return
        item = get_queue_item(self.session, self.session.current_approval_id)
        if item is None:
            self.console.print("Selected approval item was not found.")
            return
        self.session = update_approval_item(
            self.project_root,
            self.config.runtime_root,
            self.session,
            item_id=item.item_id,
            status=status,  # type: ignore[arg-type]
        )
        if status == "approved":
            self._apply_approved_item(item)
        self.console.print(f"{status}: {item.path}")

    def _print_approval_item(self, item: ApprovalQueueItem) -> None:
        self.console.print(
            "\n".join(
                [
                    f"approval_item={item.item_id}",
                    f"run_id={item.run_id}",
                    f"role={item.role}",
                    f"model={item.model}",
                    f"status={item.status}",
                    f"policy_status={item.policy_status}",
                    f"path={item.path}",
                    f"reason={item.reason}",
                ]
            )
        )
        if item.diff_path and Path(item.diff_path).exists():
            self.console.print("--- diff ---")
            for raw_line in Path(item.diff_path).read_text(encoding="utf-8").splitlines():
                if raw_line.startswith("+++ ") or raw_line.startswith("--- "):
                    self.console.print(f"[bold]{raw_line}[/bold]")
                elif raw_line.startswith("+") and not raw_line.startswith("+++"):
                    self.console.print(f"[green]{raw_line}[/green]")
                elif raw_line.startswith("-") and not raw_line.startswith("---"):
                    self.console.print(f"[red]{raw_line}[/red]")
                elif raw_line.startswith("@@"):
                    self.console.print(f"[cyan]{raw_line}[/cyan]")
                else:
                    self.console.print(raw_line)
        else:
            self.console.print("No diff available for this item.")

    def _prompt_review_choice(self, item: ApprovalQueueItem) -> None:
        self.console.print("Review choice: y=yes / n=no / d=defer / b=back")
        try:
            choice = input("review> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            self.console.print("Review prompt cancelled.")
            return
        if choice in {"y", "yes"}:
            self._update_selected_approval("approved")
            return
        if choice in {"n", "no"}:
            self._update_selected_approval("rejected")
            return
        if choice in {"d", "defer"}:
            self._update_selected_approval("deferred")
            return
        self.console.print("Left approval item unchanged.")

    def _apply_approved_item(self, item: ApprovalQueueItem) -> None:
        integration_root = self.project_root.parent / f"{self.project_root.name}-integrations"
        workspace = ensure_named_worktree(
            repository_root=self.project_root,
            workspace_root=integration_root / item.run_id,
            worktree_name="integration",
        )
        self.current_integration_workspace = workspace
        target_path = apply_proposal_to_workspace(
            workspace=workspace,
            relative_path=item.path,
            proposal_path=item.proposal_path,
        )
        self.console.print(f"applied_to={target_path}")

    def _resume_session(self) -> None:
        sessions = list_sessions(self.project_root, self.config.runtime_root, limit=20)
        if not sessions:
            self.console.print("No saved sessions found.")
            return

        table = create_table("Saved Sessions")
        table.add_column("No.")
        table.add_column("Session")
        table.add_column("Mode")
        table.add_column("Turns")
        table.add_column("Updated")
        for index, session in enumerate(sessions, start=1):
            table.add_row(
                str(index),
                session.session_id,
                session.mode,
                str(len(session.turns)),
                session.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            )
        self.console.print(table)
        self.console.print("Enter a session number to resume, or press Enter to cancel.")

        try:
            choice = input("resume> ").strip()
        except (EOFError, KeyboardInterrupt):
            self.console.print("Resume cancelled.")
            return

        if not choice:
            self.console.print("Resume cancelled.")
            return
        if not choice.isdigit():
            self.console.print("Resume cancelled. Enter a valid number next time.")
            return

        index = int(choice)
        if index < 1 or index > len(sessions):
            self.console.print("Resume cancelled. Session number out of range.")
            return

        self.session = sessions[index - 1]
        self.last_run_dir = self._derive_last_run_dir()
        self.console.print(
            f"Resumed session {self.session.session_id} with {len(self.session.turns)} saved turns."
        )

    def _derive_last_run_dir(self) -> Path | None:
        if not self.session.turns:
            return None
        run_dir = self.session.turns[-1].run_dir.strip()
        return Path(run_dir) if run_dir else None
