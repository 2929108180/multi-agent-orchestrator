from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from mao_cli.config import AppConfig, load_config
from mao_cli.orchestrator import execute_workflow
from mao_cli.providers import inspect_providers
from mao_cli.security import validate_requirement


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

    def print_welcome(self) -> None:
        self.console.print("Multi-Agent Orchestrator chat")
        self.console.print("Type a requirement to run the workflow.")
        self.console.print("Built-in commands: /help /status /doctor /last /exit")

    def run(self) -> None:
        self.print_welcome()
        while True:
            try:
                raw = input("mao> ")
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

    def _handle_command(self, line: str) -> bool:
        command = line.lower()
        if command in {"/exit", "/quit"}:
            self.console.print("Chat closed.")
            return True
        if command == "/help":
            self.console.print("Enter a product or coding requirement to run one workflow.")
            self.console.print("/status -> show session settings")
            self.console.print("/doctor -> show provider readiness for this session")
            self.console.print("/last -> show latest run directory")
            self.console.print("/exit -> leave chat")
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
        )
        self.last_run_dir = run_dir

        payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        verdicts = payload.get("verdicts") or []
        approved = verdicts[-1].get("approved") if verdicts else None
        summary = verdicts[-1].get("summary") if verdicts else "No verdict summary."

        self.console.print(f"Run artifacts saved to: {run_dir}")
        self.console.print(f"approved={approved}")
        self.console.print(f"summary={summary}")

