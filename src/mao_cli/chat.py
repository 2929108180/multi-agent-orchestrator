from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.console import Console

from mao_cli.config import AppConfig, load_config
from mao_cli.core.models import WorkflowEvent
from mao_cli.orchestrator import execute_workflow
from mao_cli.providers import inspect_providers
from mao_cli.security import validate_requirement
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
    "/last": "Show the latest run directory from this session.",
    "/exit": "Exit the chat session.",
    "/quit": "Exit the chat session.",
}


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

    def print_welcome(self) -> None:
        self.console.print("Multi-Agent Orchestrator chat")
        self.console.print("Type a requirement to run the workflow.")
        if self._interactive_completion_available():
            self.console.print("Type `/` to see commands. Use `Tab` to complete slash commands.")
        else:
            self.console.print("Type `/help` for commands. Tab completion is unavailable until `prompt_toolkit` is installed.")
        self.console.print("Built-in commands: /help /status /doctor /last /exit")

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
        command = self._resolve_command(line.lower())
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
                        f"config={self.config_path}",
                        f"mock={self.mock}",
                        f"with_worktrees={self.with_worktrees}",
                        f"output_dir={self.output_dir}",
                        f"last_run={self.last_run_dir or '-'}",
                    ]
                )
            )
            return False
        if command == "/doctor":
            rows = inspect_providers(self.config, force_mock=self.mock)
            for row in rows:
                self.console.print(
                    f"[{row.role}] adapter={row.adapter} model={row.model} ready={row.ready} note={row.note}"
                )
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
        run_dir = execute_workflow(
            requirement=requirement,
            config=self.config,
            output_dir=self.output_dir,
            repository_root=self.project_root,
            force_mock=self.mock,
            with_worktrees=self.with_worktrees,
            event_handler=self._handle_workflow_event,
        )
        self.last_run_dir = run_dir

        payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        verdicts = payload.get("verdicts") or []
        approved = verdicts[-1].get("approved") if verdicts else None
        summary = verdicts[-1].get("summary") if verdicts else "No verdict summary."

        self.console.print(f"Run artifacts saved to: {run_dir}")
        self.console.print(f"approved={approved}")
        self.console.print(f"summary={summary}")

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
        if command in CHAT_COMMANDS:
            return command
        matches = [name for name in CHAT_COMMANDS if name.startswith(command)]
        if len(matches) == 1:
            return matches[0]
        return command
