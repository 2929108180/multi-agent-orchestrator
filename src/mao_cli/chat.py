from __future__ import annotations

import json
import re
import sys
from io import StringIO
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from mao_cli.config import AppConfig, load_config
from mao_cli.core.models import WorkflowEvent
from mao_cli.gitops import WorkerWorkspace, apply_proposal_to_workspace, ensure_named_worktree
from mao_cli.mergeflow import MergeCandidate, append_merge_candidate, list_merge_candidates
from mao_cli.orchestrator import execute_workflow
from mao_cli.providers import ModelGateway, inspect_providers
from mao_cli.tool_runtime import run_with_tools
from mao_cli.registry import (
    assign_mcp_access,
    assign_skill_access,
    bind_skill_to_mcp,
    filter_mcp_servers_for,
    filter_skills_for,
    import_local_mcp,
    import_local_skills,
    load_mcp_registry,
    register_mcp_server,
    register_skill,
    registered_or_discovered_skills,
)
from mao_cli.security import ensure_project_path, validate_requirement
from mao_cli.sessions import (
    ApprovalQueueItem,
    ChatSessionState,
    append_approval_items,
    append_turn,
    append_transcript_entry,
    bounded_role_memory,
    build_conversation_context,
    build_review_memory,
    build_task_memory,
    clear_turns,
    create_session,
    get_queue_item,
    load_latest_session,
    load_session,
    list_sessions,
    export_session_markdown,
    replay_lines,
    save_session,
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
    "/team": "Show or set team mode: auto / on / off.",
    "/members": "Show current team member enablement.",
    "/member": "Enable or disable a team member: on/off <role>.",
    "/history": "Show the saved turns for this session.",
    "/context": "Show the conversation context sent into new runs.",
    "/clear": "Clear the saved turns in the current session.",
    "/skills": "List available local skills for team mode.",
    "/mcp": "List registered MCP servers for team mode.",
    "/skill-import-local": "Import local skills into the registry.",
    "/mcp-import-local": "Import local MCP servers into the registry.",
    "/grant-skill": "Grant a role or model access to one registered skill.",
    "/grant-mcp": "Grant a role or model access to one registered MCP server.",
    "/register-skill": "Register one skill into the registry.",
    "/register-mcp": "Register one MCP server into the registry.",
    "/bind-skill": "Bind a skill to an MCP tool: <skill> <server> <tool>.",
    "/resume": "Choose and resume a saved session from this chat window.",
    "/queue": "List queued approval items.",
    "/review": "Show the currently selected approval item.",
    "/pick": "Open a specific approval item by queue number.",
    "/approve": "Approve the currently selected queued change.",
    "/reject": "Reject the currently selected queued change.",
    "/defer": "Pause the current approval item and come back later.",
    "/last": "Show the latest run directory from this session.",
    "/export": "Export this session transcript as markdown.",
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
        self.team_mode = "auto"
        self.member_states = {
            "frontend": True,
            "backend": True,
            "integration": True,
            "reviewer": True,
        }
        self._auto_approve_tools = False
        self._preflight_live_mode()

    def print_welcome(self) -> None:
        self.console.print(self._build_banner())
        self._say("[bold white]Multi-Agent Orchestrator chat[/bold white]", record=False)
        self._say("[cyan]Type a requirement to run the workflow.[/cyan]", record=False)
        self._say(
            f"[white]session={self.session.session_id}[/white] "
            f"[green]mode={'mock' if self.mock else 'live'}[/green] "
            f"[magenta]skills={len(self.skills)}[/magenta] "
            f"[cyan]team={self.team_mode}[/cyan]",
            record=False,
        )
        if self._interactive_completion_available():
            self._say("[green]Type `/` to see commands. Use `Tab` to complete slash commands.[/green]", record=False)
        else:
            self._say(
                "[yellow]Type `/help` for commands. Tab completion is unavailable until `prompt_toolkit` is installed.[/yellow]",
                record=False,
            )
        self._say(
            "[magenta]Built-in commands:[/magenta] "
            "/help /status /doctor /mode /team /members /member /history /context /skills /mcp /merge "
            "/skill-import-local /mcp-import-local /grant-skill /grant-mcp "
            "/register-skill /register-mcp /resume /queue /review /approve /reject /defer /last /export /exit",
            record=False,
        )

    def run(self) -> None:
        self.print_welcome()
        self._replay_transcript_if_needed()
        while True:
            try:
                raw = self._prompt()
            except EOFError:
                self.console.print("Chat closed.")
                return
            except KeyboardInterrupt:
                self.console.print("\nChat interrupted.")
                return

            line = raw.lstrip("\ufeff").strip()
            if line.startswith("锘?"):
                line = line[2:].strip()
            if line.startswith("锘?/"):
                line = line.replace("锘?", "", 1).strip()
            if not line:
                continue
            if "/" in line and not line.startswith("/") and line.index("/") <= 4:
                line = line[line.index("/") :].strip()
            self.session = append_transcript_entry(
                self.project_root,
                self.config.runtime_root,
                self.session,
                speaker="user",
                content=line,
            )
            if line.startswith("/"):
                if self._handle_command(line):
                    return
                continue

            self._handle_user_request(line)

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
            self._say("Chat closed.")
            return True
        if command == "/help":
            table = create_table("Chat Commands")
            table.add_column("Command")
            table.add_column("Purpose")
            for name, purpose in CHAT_COMMANDS.items():
                table.add_row(name, purpose)
            self._say("Enter a product or coding requirement to run one workflow.")
            self._say_renderable(table)
            return False
        if command == "/status":
            self._say(
                "\n".join(
                    [
                        f"session_id={self.session.session_id}",
                        f"config={self.config_path}",
                        f"mock={self.mock}",
                        f"team_mode={self.team_mode}",
                        f"members={self._member_state_summary()}",
                        f"with_worktrees={self.with_worktrees}",
                        f"output_dir={self.output_dir}",
                        f"last_run={self.last_run_dir or '-'}",
                        f"turns={len(self.session.turns)}",
                    ]
                )
            )
            return False
        if command == "/mode":
            self._say(f"mode={'mock' if self.mock else 'live'}")
            return False
        if command == "/team":
            self._handle_team_command(argument)
            return False
        if command == "/members":
            self._print_members()
            return False
        if command == "/member":
            self._handle_member_command(argument)
            return False
        if command == "/doctor":
            rows = inspect_providers(self.config, force_mock=self.mock)
            for row in rows:
                self._say(
                    f"[{row.role}] adapter={row.adapter} model={row.model} ready={row.ready} note={row.note}"
                )
            return False
        if command == "/history":
            self._print_history()
            return False
        if command == "/context":
            context = build_conversation_context(self.session)
            self._say(context or "No conversation context yet.")
            return False
        if command == "/clear":
            self.session = clear_turns(self.project_root, self.config.runtime_root, self.session)
            self.last_run_dir = None
            self._say("Session turns cleared.")
            return False
        if command == "/skills":
            self._print_skills()
            return False
        if command == "/mcp":
            self._print_mcp_servers()
            return False
        if command == "/merge":
            self._print_merge_candidates()
            return False
        if command == "/skill-import-local":
            self._import_local_skills()
            return False
        if command == "/mcp-import-local":
            self._import_local_mcp()
            return False
        if command == "/grant-skill":
            self._grant_skill(argument)
            return False
        if command == "/grant-mcp":
            self._grant_mcp(argument)
            return False
        if command == "/register-skill":
            self._register_skill(argument)
            return False
        if command == "/register-mcp":
            self._register_mcp(argument)
            return False
        if command == "/bind-skill":
            self._bind_skill(argument)
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
                self._say("No run has been executed in this chat session yet.")
                return False
            self._say(f"last_run={self.last_run_dir}")
            return False

        if command == "/export":
            export_path = self._export_session_markdown(argument)
            # Export helper already records the assistant line into the transcript.
            self._say(f"exported={export_path}", record=False)
            return False

        self._say(f"Unknown command: {line}. Use /help.")
        return False

    def _handle_user_request(self, requirement: str) -> None:
        if self._should_use_team_mode(requirement):
            self._run_requirement(requirement)
            return
        self._run_single_model(requirement)

    def _run_requirement(self, requirement: str) -> None:
        try:
            requirement = validate_requirement(requirement)
        except ValueError as exc:
            self._say(f"Invalid requirement: {exc}")
            return

        self._say("Running workflow...")
        conversation_context = build_conversation_context(self.session)
        task_memories = {
            "frontend": build_task_memory(self.session, "frontend"),
            "backend": build_task_memory(self.session, "backend"),
        }
        role_memories = dict(self.session.role_memories or {})
        review_memory = build_review_memory(self.session)
        capability_contexts = {
            role: self._build_capability_context(role)
            for role in ("frontend", "backend", "integration", "reviewer")
        }
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
            role_memories=role_memories,
            review_memory=review_memory,
            capability_contexts=capability_contexts,
            enabled_roles={role for role, enabled in self.member_states.items() if enabled}.union({"architect"}),
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
        self._update_role_memories_from_run(
            requirement=requirement,
            run_dir=run_dir,
            conversation_context=conversation_context,
        )

        self._say(f"Run artifacts saved to: {run_dir}")
        self._say(f"approved={approved}")
        self._say(f"summary={summary}")
        pending = [item for item in self.session.approval_queue if item.status in {"pending", "deferred"}]
        if pending:
            self._say(f"approval_queue={len(pending)} pending items. Use /queue or /review.")

    def _confirm_tool_call(self, tool_name: str, description: str, args_summary: str) -> bool:
        """Prompt the user to confirm a destructive tool call.

        Returns True if allowed, False if denied.
        Supports:
          y = yes (allow this one)
          n = no (deny)
          a = allow all destructive tools for this session
        """
        if getattr(self, "_auto_approve_tools", False):
            return True

        self.console.print(
            f"\n[bold yellow]Tool requires confirmation:[/bold yellow]\n"
            f"  [cyan]{tool_name}[/cyan] — {description}\n"
            f"  args: {args_summary}\n"
        )
        try:
            choice = input("[y]es / [n]o / [a]llow all this session: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False

        if choice in {"a", "allow"}:
            self._auto_approve_tools = True
            return True
        return choice in {"y", "yes"}

    def _run_single_model(self, requirement: str) -> None:
        try:
            requirement = validate_requirement(requirement)
        except ValueError as exc:
            self._say(f"Invalid requirement: {exc}")
            return

        self._say("calling architect...")
        gateway = ModelGateway(config=self.config, force_mock=self.mock)

        base_prompt = "\n".join(
            [
                "You are the primary assistant — an intelligent, autonomous, context-aware agent.",
                "You think deeply, reason about intent, and proactively explore the codebase before acting.",
                "You are NOT a passive command executor. You are a skilled engineer who understands WHY.",
                "",
                "# PHASE 1: DEEP UNDERSTANDING (do this mentally before ANY action)",
                "",
                "Before responding or using any tool, answer these questions internally:",
                "- What is the user's REAL goal? (not the literal words — the underlying intent)",
                "- What context do I need to do this well?",
                "- What could go wrong if I act without full understanding?",
                "",
                "Examples of intent inference:",
                "- '改为古诗词春晓' → user wants the COMPLETE poem 《春晓》 by 孟浩然 (all lines), not just the title",
                "- '加个登录功能' → a fully working login feature with proper validation, not an empty stub",
                "- '修复这个bug' → find root cause, understand why it happens, then fix properly",
                "- '把这个函数改成异步' → read the function, understand all callers, update them all",
                "- '优化这段代码' → read it, understand the bottleneck, propose a real improvement",
                "",
                "RULE: When the user references something by name (a poem, a protocol, an algorithm, a pattern),",
                "you MUST deliver the COMPLETE, CORRECT, CANONICAL version. Never a fragment, placeholder, or summary.",
                "",
                "# PHASE 2: AUTONOMOUS CONTEXT GATHERING (use tools to explore BEFORE modifying)",
                "",
                "You are an autonomous agent. When a task involves code, you MUST gather context first:",
                "",
                "A) **Locate**: If the user mentions a file/function/class but not the exact path:",
                "   - Use mao_fs.mao_fs_list_dir to browse directories",
                "   - Search multiple levels deep if needed (list parent dir, then subdirs)",
                "   - NEVER guess a path. NEVER invent a filename.",
                "",
                "B) **Read before edit**: Before modifying ANY file:",
                "   - Read the ENTIRE target file with mao_fs.mao_fs_read_text",
                "   - Understand its structure, imports, dependencies, coding style",
                "   - Identify what the user's change will affect",
                "",
                "C) **Trace dependencies**: When changing a function/class/variable:",
                "   - Think: who calls this? what imports this? what depends on this?",
                "   - If the change affects interfaces, read the callers/importers too",
                "   - A change in one place often requires changes in related files",
                "",
                "D) **Understand the neighborhood**: Before writing new code:",
                "   - Read nearby files to understand the project's patterns and conventions",
                "   - Match the existing style (naming, error handling, structure)",
                "   - Don't introduce alien patterns into an established codebase",
                "",
                "E) **Multi-step exploration**: For complex tasks, chain multiple tool calls:",
                "   - Step 1: List directory to find relevant files",
                "   - Step 2: Read the target file",
                "   - Step 3: Read related files (imports, callers, tests)",
                "   - Step 4: NOW make the change with full context",
                "",
                "# PHASE 3: INTELLIGENT EXECUTION",
                "",
                "When producing output:",
                "- Deliver COMPLETE results. Never partial. Never 'the rest stays the same'.",
                "- If implementing a feature, write the FULL implementation.",
                "- If writing content (poem, config, doc), write ALL of it.",
                "- If modifying code, produce the complete modified version.",
                "- If multiple files need changes, address ALL of them.",
                "",
                "Quality checks before responding:",
                "- Does my output fulfill the user's REAL intent (not just literal words)?",
                "- Is it COMPLETE? (no missing pieces, no TODOs, no placeholders)",
                "- Is it CORRECT? (no syntax errors, no broken imports, no logic bugs)",
                "- Is it CONSISTENT with the codebase style?",
                "- Did I miss any related files that also need changes?",
                "",
                "# PHASE 4: PROACTIVE INTELLIGENCE",
                "",
                "- If you notice a bug, security issue, or improvement opportunity while working, mention it.",
                "- If the request is ambiguous, state your interpretation and proceed (don't just stop).",
                "- If you discover the user's approach won't work, explain why and suggest a better alternative.",
                "- If a change breaks something else, fix that too or clearly flag it.",
                "",
                "# Tool Protocol",
                "",
                "You have tools in the catalog below. Use them as an autonomous agent would:",
                "- EXPLORE first (list dirs, read files) → UNDERSTAND → then ACT (write/modify)",
                "- For file operations: NEVER invent paths. List dirs or read to discover real paths.",
                "- If the user gives only a filename, search for it with mao_fs.mao_fs_list_dir.",
                "- If multiple matches exist, report them and ask which one.",
                "- ARGS_JSON must be valid one-line JSON. Omit optional fields to use defaults.",
                "",
                f"User input: {requirement}",
            ]
        )

        confirm_cb = self._confirm_tool_call if self._interactive_tty_available() else None

        response, _tool_trace = run_with_tools(
            gateway=gateway,
            role="architect",
            base_prompt=base_prompt,
            project_root=self.project_root,
            runtime_root=self.config.runtime_root,
            config=self.config,
            event_handler=self._handle_workflow_event,
            run_id="",
            round_index=0,
            confirm_callback=confirm_cb,
        )

        self._say(response)
        self.session = append_turn(
            self.project_root,
            self.config.runtime_root,
            self.session,
            user_input=requirement,
            run_id="",
            run_dir=Path(),
            approved=None,
            summary=response,
            defects=[],
        )

    def _should_use_team_mode(self, requirement: str) -> bool:
        if self.team_mode == "on":
            return True
        if self.team_mode == "off":
            return False
        if self._looks_like_direct_fs_request(requirement):
            return False
        if self.mock:
            return self._heuristic_should_use_team_mode(requirement)
        return self._supervisor_should_use_team_mode(requirement)

    def _looks_like_direct_fs_request(self, requirement: str) -> bool:
        """Detect direct file CRUD requests that should stay in single-model mode."""
        text = requirement.strip()
        lowered = text.lower()

        action_patterns = [
            r"\b(create|write|read|list|delete|remove|mkdir|edit|update|overwrite)\b",
            r"(创建|写入|读取|读出|列出|删除|移除|新建|修改|覆盖|目录|文件夹|文件)",
        ]
        path_patterns = [
            r"[A-Za-z0-9_\-./\\]+\.[A-Za-z0-9]{1,16}",
            r"(?<![A-Za-z])(?:\.{0,2}[\\/])?[A-Za-z0-9_\-./\\]+[\\/][A-Za-z0-9_\-./\\]+",
            r"`[^`]+`",
        ]
        feature_signals = [
            "frontend",
            "backend",
            "api",
            "react",
            "vite",
            "fastapi",
            "system",
            "project",
            "应用",
            "前端",
            "后端",
            "接口",
            "系统",
            "项目",
        ]

        has_action = any(re.search(pattern, lowered if "\\b" in pattern else text, re.IGNORECASE) for pattern in action_patterns)
        has_path = any(re.search(pattern, text) for pattern in path_patterns)
        if not (has_action and has_path):
            return False
        return not any(token in lowered for token in feature_signals)

    def _heuristic_should_use_team_mode(self, requirement: str) -> bool:
        lowered = requirement.lower()
        casual_inputs = {
            "hi",
            "hello",
            "你好",
            "嗨",
            "哈喽",
            "在吗",
            "早上好",
            "晚上好",
        }
        if lowered.strip() in casual_inputs:
            return False
        teamwork_signals = [
            "build",
            "create",
            "make",
            "implement",
            "project",
            "app",
            "task",
            "tracker",
            "frontend",
            "backend",
            "react",
            "vite",
            "fastapi",
            "api",
            "reviewer",
            "审查",
            "前端",
            "后端",
            "接口",
            "系统",
            "项目",
            "登录",
            "权限",
        ]
        if "\n" in requirement or len(requirement) > 20:
            return True
        return any(token in lowered for token in teamwork_signals)

    def _supervisor_should_use_team_mode(self, requirement: str) -> bool:
        gateway = ModelGateway(config=self.config, force_mock=self.mock)
        prompt = "\n".join(
            [
                "You are the supervisor routing assistant.",
                "Decide whether this input requires the whole team workflow or a direct single-model reply.",
                "Return exactly one line:",
                "TEAM_MODE: on or TEAM_MODE: off",
                f"User input: {requirement}",
            ]
        )

        if self._interactive_tty_available():
            with self.console.status("Deciding routing..."):
                response = gateway.complete(role="architect", prompt=prompt)
        else:
            response = gateway.complete(role="architect", prompt=prompt)
        first_line = response.splitlines()[0].strip().lower()
        return "team_mode: on" in first_line

    def _interactive_completion_available(self) -> bool:
        return PromptSession is not None and self._interactive_tty_available()

    def _interactive_tty_available(self) -> bool:
        return sys.stdin.isatty() and sys.stdout.isatty()

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
            self._say(line)

    def _format_event(self, event: WorkflowEvent) -> str:
        role = event.role or "workflow"
        model = event.model or ""
        prefix = self._event_prefix(role=role, model=model)
        if event.event_type == "workflow_started":
            return "workflow: started"
        if event.event_type == "tool_call_started":
            name = (event.metadata or {}).get("name", "")
            return f"{prefix} tool -> {name}"
        if event.event_type == "tool_call_completed":
            name = (event.metadata or {}).get("name", "")
            ok = (event.metadata or {}).get("ok", "")
            suffix = f" ok={ok}" if ok else ""
            return f"{prefix} tool <- {name}{suffix}"
        if event.event_type == "architect_started":
            return f"{prefix} planning"
        if event.event_type == "architect_dispatched":
            return f"{prefix} dispatch -> {event.message}"
        if event.event_type == "architect_completed":
            return f"{prefix} {event.message}"
        if event.event_type == "frontend_started":
            return f"{prefix} {event.message}"
        if event.event_type == "backend_started":
            return f"{prefix} {event.message}"
        if event.event_type == "frontend_completed":
            return f"{prefix} {event.message}"
        if event.event_type == "backend_completed":
            return f"{prefix} {event.message}"
        if event.event_type == "review_started":
            return f"{prefix} {event.message}"
        if event.event_type == "review_completed":
            return f"{prefix} {event.message}"
        if event.event_type == "repair_round_started":
            return f"repair round {event.round_index}"
        if event.event_type == "repair_target_started":
            return f"{prefix} repairing"
        if event.event_type == "repair_target_completed":
            return f"{prefix} repaired"
        if event.event_type == "workflow_completed":
            return "workflow: completed"
        if event.event_type == "workflow_recap":
            return f"final recap: {event.message}"
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

    def _handle_team_command(self, argument: str) -> None:
        value = argument.strip().lower()
        if not value:
            self._say(f"team_mode={self.team_mode}")
            return
        if value not in {"auto", "on", "off"}:
            self._say("Use `/team auto`, `/team on`, or `/team off`.")
            return
        self.team_mode = value
        self._say(f"team_mode set to {self.team_mode}")

    def _print_members(self) -> None:
        table = create_table("Team Members")
        table.add_column("Role")
        table.add_column("Enabled")
        table.add_column("Model")
        for role in ("frontend", "backend", "integration", "reviewer"):
            table.add_row(role, str(self.member_states[role]), self.config.providers[role].model)
        self._say_renderable(table)

    def _handle_member_command(self, argument: str) -> None:
        parts = argument.split()
        if len(parts) != 2 or parts[0] not in {"on", "off"}:
            self._say("Use `/member on <role>` or `/member off <role>`.")
            return
        _, role = parts
        if role not in self.member_states:
            self._say("Allowed roles: frontend, backend, integration, reviewer.")
            return
        self.member_states[role] = parts[0] == "on"
        self._say(f"member {role} set to {self.member_states[role]}")

    def _summarize_text(self, text: str, limit: int = 120) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."

    def _member_state_summary(self) -> str:
        return ", ".join(f"{role}={'on' if enabled else 'off'}" for role, enabled in self.member_states.items())

    def _event_prefix(self, *, role: str, model: str) -> str:
        styles = {
            "architect": "bold cyan",
            "frontend": "bold magenta",
            "backend": "bold green",
            "integration": "bold blue",
            "reviewer": "bold yellow",
        }
        style = styles.get(role, "bold white")
        label = f"{role}[{model}]" if model else role
        return f"[{style}]{label}[/]"

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

    def _build_capability_context(self, role: str) -> str:
        model = self.config.providers[role].model
        skills = filter_skills_for(
            self.project_root,
            self.config.runtime_root,
            role=role,
            model=model,
        )
        mcp_servers = filter_mcp_servers_for(
            self.project_root,
            self.config.runtime_root,
            role=role,
            model=model,
        )
        lines = [f"Capabilities for {role} ({model}):"]
        if skills:
            lines.append("Skills:")
            for entry in skills[:8]:
                lines.append(f"- {entry.name}: {entry.description}")
        if mcp_servers:
            lines.append("MCP servers:")
            for entry in mcp_servers[:8]:
                lines.append(f"- {entry.name}: transport={entry.transport}")
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
            self._say("No saved turns in this session yet.")
            return
        table = create_table("Session History")
        table.add_column("Turn")
        table.add_column("Approved")
        table.add_column("Summary")
        for turn in self.session.turns[-10:]:
            table.add_row(turn.turn_id, str(turn.approved), turn.summary)
        self._say_renderable(table)

    def _print_skills(self) -> None:
        if not self.skills:
            self._say("No local skills discovered.")
            return
        table = create_table("Available Skills")
        table.add_column("Name")
        table.add_column("Description")
        for skill in self.skills[:20]:
            table.add_row(skill.name, skill.description)
        self._say_renderable(table)

    def _print_mcp_servers(self) -> None:
        servers = load_mcp_registry(self.project_root, self.config.runtime_root)
        if not servers:
            self._say("No MCP servers registered.")
            return
        table = create_table("Registered MCP Servers")
        table.add_column("Name")
        table.add_column("Transport")
        table.add_column("Source")
        for server in servers:
            table.add_row(server.name, server.transport, server.source)
        self._say_renderable(table)

    def _print_merge_candidates(self) -> None:
        candidates = list_merge_candidates(self.project_root, self.config.runtime_root, limit=20)
        if not candidates:
            self._say("No merge candidates available.")
            return
        table = create_table("Merge Candidates")
        table.add_column("Candidate")
        table.add_column("Run")
        table.add_column("Role")
        table.add_column("Path")
        table.add_column("Status")
        table.add_column("Shared")
        for item in candidates:
            table.add_row(
                item.candidate_id,
                item.run_id,
                item.role,
                item.path,
                item.status,
                str(item.shared_file),
            )
        self._say_renderable(table)

    def _import_local_skills(self) -> None:
        target = import_local_skills(self.project_root, self.config.runtime_root)
        self.skills = registered_or_discovered_skills(self.project_root, self.config.runtime_root)
        self.team_context = self._build_team_context()
        self._say(f"skills imported -> {target}")

    def _import_local_mcp(self) -> None:
        target = import_local_mcp(self.project_root, self.config.runtime_root)
        self._say(f"mcp imported -> {target}")

    def _grant_skill(self, argument: str) -> None:
        parts = argument.split()
        if len(parts) != 3 or parts[0] not in {"role", "model"}:
            self._say("Use `/grant-skill role <role> <skill>` or `/grant-skill model <model> <skill>`.")
            return
        kind, target, skill_name = parts
        path = assign_skill_access(
            self.project_root,
            self.config.runtime_root,
            name=skill_name,
            role=target if kind == "role" else None,
            model=target if kind == "model" else None,
        )
        self.skills = registered_or_discovered_skills(self.project_root, self.config.runtime_root)
        self.team_context = self._build_team_context()
        self._say(f"skill grant updated -> {path}")

    def _grant_mcp(self, argument: str) -> None:
        parts = argument.split()
        if len(parts) != 3 or parts[0] not in {"role", "model"}:
            self._say("Use `/grant-mcp role <role> <server>` or `/grant-mcp model <model> <server>`.")
            return
        kind, target, server_name = parts
        path = assign_mcp_access(
            self.project_root,
            self.config.runtime_root,
            name=server_name,
            role=target if kind == "role" else None,
            model=target if kind == "model" else None,
        )
        self._say(f"mcp grant updated -> {path}")

    def _register_skill(self, argument: str) -> None:
        parts = argument.split(" ", 2)
        if len(parts) != 3:
            self._say("Use `/register-skill <name> <path> <description>`.")
            return
        name, path, description = parts
        target = register_skill(
            self.project_root,
            self.config.runtime_root,
            name=name,
            description=description,
            path=path,
        )
        self.skills = registered_or_discovered_skills(self.project_root, self.config.runtime_root)
        self.team_context = self._build_team_context()
        self._say(f"skill registered -> {target}")

    def _register_mcp(self, argument: str) -> None:
        parts = argument.split()
        if len(parts) < 3:
            self._say("Use `/register-mcp <name> <transport> <command|url> [args...]`.")
            return
        name, transport, endpoint, *rest = parts
        kwargs = {"name": name, "transport": transport}
        if transport == "stdio":
            kwargs["command"] = endpoint
            kwargs["args"] = rest
        else:
            kwargs["url"] = endpoint
        target = register_mcp_server(
            self.project_root,
            self.config.runtime_root,
            **kwargs,
        )
        self._say(f"mcp registered -> {target}")

    def _bind_skill(self, argument: str) -> None:
        parts = argument.split()
        if len(parts) != 3:
            self._say("Use `/bind-skill <skill> <server> <tool>`. Example: `/bind-skill pdf mao_mcp mao_read_project_doc`.")
            return
        skill, server, tool = parts
        target = bind_skill_to_mcp(
            self.project_root,
            self.config.runtime_root,
            skill=skill,
            server=server,
            tool=tool,
        )
        self.skills = registered_or_discovered_skills(self.project_root, self.config.runtime_root)
        self.team_context = self._build_team_context()
        self._say(f"skill bound -> {skill} -> {server}.{tool}")
        self._say(f"registry={target}")

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

    def _update_role_memories_from_run(self, *, requirement: str, run_dir: Path, conversation_context: str) -> None:
        """Update per-role long-lived memories after a workflow run.

        Notes:
        - Uses the architect to produce bounded summaries.
        - Prompt explicitly forbids repeating raw user input.
        """

        try:
            payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        except Exception:
            return

        exchanges = payload.get("exchanges") or []
        verdicts = payload.get("verdicts") or []

        def _exchange(role: str) -> str:
            item = next((ex for ex in exchanges if ex.get("role") == role), None)
            return item.get("response", "") if isinstance(item, dict) and item else ""

        reviewer_summary = ""
        reviewer_defects: list[str] = []
        if verdicts:
            last_verdict = verdicts[-1]
            if isinstance(last_verdict, dict):
                reviewer_summary = str(last_verdict.get("summary", "") or "")
                defects = last_verdict.get("defects") or []
                if isinstance(defects, list):
                    for defect in defects:
                        if isinstance(defect, dict):
                            summary = defect.get("summary") or defect.get("title") or ""
                            if summary:
                                reviewer_defects.append(str(summary))
                        elif isinstance(defect, str):
                            reviewer_defects.append(defect)

        role_briefs: dict[str, str] = {}
        briefs_exchange = next((ex for ex in exchanges if ex.get("role") == "architect" and "ROLE_BRIEFS:" in (ex.get("response") or "")), None)
        if isinstance(briefs_exchange, dict):
            raw = briefs_exchange.get("response") or ""
            if isinstance(raw, str):
                for line in raw.splitlines():
                    if ":" not in line:
                        continue
                    key, value = line.split(":", 1)
                    k = key.strip().lower()
                    if k in {"frontend", "backend", "integration", "reviewer"}:
                        role_briefs[k] = value.strip()

        gateway = ModelGateway(config=self.config, force_mock=self.mock)

        previous_memories = dict(self.session.role_memories or {})

        update_prompt = "\n".join(
            [
                "You are the architect.",
                "Update long-lived per-role working memories for future runs.",
                "CRITICAL RULES:",
                "- Do NOT quote or reproduce raw user input verbatim.",
                "- Do NOT include secrets, API keys, or long transcripts.",
                "- Be concise; focus on stable decisions, interfaces, constraints, and unresolved issues.",
                "- Each role memory should be a compact summary (bullets ok).",
                "Output ONLY this block and nothing else:",
                "ROLE_MEMORIES:",
                "FRONTEND: ...",
                "BACKEND: ...",
                "INTEGRATION: ...",
                "REVIEWER: ...",
                "END_ROLE_MEMORIES",
                "",
                f"Conversation context (already summarized):\n{conversation_context}",
                "",
                f"User input (for reference only; do not quote): {requirement}",
                "",
                "Role briefs (already summarized):",
                f"FRONTEND_BRIEF: {role_briefs.get('frontend','')}",
                f"BACKEND_BRIEF: {role_briefs.get('backend','')}",
                f"INTEGRATION_BRIEF: {role_briefs.get('integration','')}",
                f"REVIEWER_BRIEF: {role_briefs.get('reviewer','')}",
                "",
                "Worker outputs (summaries/proposals):",
                f"FRONTEND_OUTPUT: {_exchange('frontend')}",
                f"BACKEND_OUTPUT: {_exchange('backend')}",
                f"INTEGRATION_OUTPUT: {_exchange('integration')}",
                f"REVIEWER_SUMMARY: {reviewer_summary}",
                f"REVIEWER_DEFECTS: {'; '.join(reviewer_defects)}",
                "",
                "Previous role memories:",
                f"FRONTEND_PREV: {previous_memories.get('frontend','')}",
                f"BACKEND_PREV: {previous_memories.get('backend','')}",
                f"INTEGRATION_PREV: {previous_memories.get('integration','')}",
                f"REVIEWER_PREV: {previous_memories.get('reviewer','')}",
            ]
        )

        response, _tool_trace = run_with_tools(
            gateway=gateway,
            role="architect",
            base_prompt=update_prompt,
            project_root=self.project_root,
            runtime_root=self.config.runtime_root,
            config=self.config,
            event_handler=self._handle_workflow_event,
            run_id=str(payload.get("run_id", "")),
            round_index=0,
        )

        if not isinstance(response, str) or not response.strip():
            return

        new_memories: dict[str, str] = {}
        in_block = False
        for raw_line in response.splitlines():
            line = raw_line.strip()
            if line == "ROLE_MEMORIES:":
                in_block = True
                continue
            if line == "END_ROLE_MEMORIES":
                break
            if not in_block:
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            k = key.strip().lower()
            v = value.strip()
            if k in {"frontend", "backend", "integration", "reviewer"}:
                new_memories[k] = bounded_role_memory(v)

        if not new_memories:
            return

        self.session.role_memories.update(new_memories)
        self.session.role_memories = {k: bounded_role_memory(v) for k, v in self.session.role_memories.items()}
        save_session(self.project_root, self.config.runtime_root, self.session)

    def _print_queue(self) -> None:
        if not self.session.approval_queue:
            self._say("No approval items queued.")
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
        self._say_renderable(table)

    def _show_selected_approval(self) -> None:
        if not self.session.current_approval_id:
            self._say("No approval item is currently selected.")
            return
        item = get_queue_item(self.session, self.session.current_approval_id)
        if item is None:
            self._say("Selected approval item was not found.")
            return
        self._print_approval_item(item)
        self._prompt_review_choice(item)

    def _pick_approval(self, argument: str) -> None:
        if not argument.isdigit():
            self._say("Use `/pick <number>` to open one approval item.")
            return
        index = int(argument)
        if index < 1 or index > len(self.session.approval_queue):
            self._say("Approval item number is out of range.")
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
            self._say("No approval item is currently selected.")
            return
        item = get_queue_item(self.session, self.session.current_approval_id)
        if item is None:
            self._say("Selected approval item was not found.")
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
        self._say(f"{status}: {item.path}")

    def _print_approval_item(self, item: ApprovalQueueItem) -> None:
        self._say(
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
            self._say("--- diff ---")
            for raw_line in Path(item.diff_path).read_text(encoding="utf-8").splitlines():
                if raw_line.startswith("+++ ") or raw_line.startswith("--- "):
                    self._say(f"[bold]{raw_line}[/bold]")
                elif raw_line.startswith("+") and not raw_line.startswith("+++"):
                    self._say(f"[green]{raw_line}[/green]")
                elif raw_line.startswith("-") and not raw_line.startswith("---"):
                    self._say(f"[red]{raw_line}[/red]")
                elif raw_line.startswith("@@"):
                    self._say(f"[cyan]{raw_line}[/cyan]")
                else:
                    self._say(raw_line)
        else:
            self._say("No diff available for this item.")

    def _prompt_review_choice(self, item: ApprovalQueueItem) -> None:
        self._say("Review choice: y=yes / n=no / d=defer / b=back")
        try:
            choice = input("review> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            self._say("Review prompt cancelled.")
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
        self._say("Left approval item unchanged.")

    def _apply_approved_item(self, item: ApprovalQueueItem) -> None:
        if item.shared_file:
            self._say("shared file routed to integration actor")
            self.session = update_approval_item(
                self.project_root,
                self.config.runtime_root,
                self.session,
                item_id=item.item_id,
                status="blocked_shared",
            )
            candidate = MergeCandidate(
                run_id=item.run_id,
                item_id=item.item_id,
                role=item.role,
                path=item.path,
                model=item.model,
                integration_workspace="",
                applied_path="",
                shared_file=True,
                status="blocked_shared",
                reason=item.reason,
            )
            target = append_merge_candidate(self.project_root, self.config.runtime_root, candidate)
            queue_item = get_queue_item(self.session, item.item_id)
            if queue_item is not None:
                queue_item.merge_candidate_id = candidate.candidate_id
            self._say(f"merge_candidate={candidate.candidate_id}")
            self._say(f"merge_registry={target}")
            return

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
        candidate = MergeCandidate(
            run_id=item.run_id,
            item_id=item.item_id,
            role=item.role,
            path=item.path,
            model=item.model,
            integration_workspace=workspace.path,
            applied_path=str(target_path),
            shared_file=False,
            status="ready_for_merge",
            reason=item.reason,
        )
        target = append_merge_candidate(self.project_root, self.config.runtime_root, candidate)
        self.session = update_approval_item(
            self.project_root,
            self.config.runtime_root,
            self.session,
            item_id=item.item_id,
            status="applied_to_integration",
        )
        queue_item = get_queue_item(self.session, item.item_id)
        if queue_item is not None:
            queue_item.merge_candidate_id = candidate.candidate_id
        self._say(f"applied_to={target_path}")
        self._say(f"merge_candidate={candidate.candidate_id}")
        self._say(f"merge_registry={target}")

    def _export_session_markdown(self, argument: str) -> Path:
        runtime_root = self.config.runtime_root
        default_target = self.project_root / runtime_root / "sessions" / f"{self.session.session_id}.md"

        if argument.strip():
            target = ensure_project_path(self.project_root, Path(argument.strip()), must_exist=False, label="output")
        else:
            target = default_target

        target.parent.mkdir(parents=True, exist_ok=True)

        # Record the export action into the transcript before rendering markdown,
        # so the export output is included in the exported file.
        self.session = append_transcript_entry(
            self.project_root,
            runtime_root,
            self.session,
            speaker="assistant",
            content=f"exported={target}",
        )
        target.write_text(export_session_markdown(self.session), encoding="utf-8")
        return target

    def _resume_session(self) -> None:
        sessions = list_sessions(self.project_root, self.config.runtime_root, limit=20)
        if not sessions:
            self._say("No saved sessions found.")
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
        self._say_renderable(table)
        self._say("Enter a session number to resume, or press Enter to cancel.")

        try:
            choice = input("resume> ").strip()
        except (EOFError, KeyboardInterrupt):
            self._say("Resume cancelled.")
            return

        if not choice:
            self._say("Resume cancelled.")
            return
        if not choice.isdigit():
            self._say("Resume cancelled. Enter a valid number next time.")
            return

        index = int(choice)
        if index < 1 or index > len(sessions):
            self._say("Resume cancelled. Session number out of range.")
            return

        self.session = sessions[index - 1]
        self.last_run_dir = self._derive_last_run_dir()
        self._say(
            f"Resumed session {self.session.session_id} with {len(self.session.turns)} saved turns."
        )
        self._replay_transcript_if_needed()

    def _derive_last_run_dir(self) -> Path | None:
        if not self.session.turns:
            return None
        run_dir = self.session.turns[-1].run_dir.strip()
        return Path(run_dir) if run_dir else None

    def _say(self, message: str, *, record: bool = True) -> None:
        self.console.print(message)
        if record:
            self.session = append_transcript_entry(
                self.project_root,
                self.config.runtime_root,
                self.session,
                speaker="assistant",
                content=self._render_plain_text(message),
            )

    def _say_renderable(self, renderable, *, record: bool = True) -> None:
        self.console.print(renderable)
        if record:
            self.session = append_transcript_entry(
                self.project_root,
                self.config.runtime_root,
                self.session,
                speaker="assistant",
                content=self._render_plain_text(renderable),
            )

    def _render_plain_text(self, renderable) -> str:
        capture = StringIO()
        plain_console = Console(file=capture, force_terminal=False, color_system=None, width=120)
        plain_console.print(renderable)
        return capture.getvalue().strip()

    def _replay_transcript_if_needed(self) -> None:
        lines = replay_lines(self.session)
        if not lines:
            return
        self.console.print("[bold cyan]Replaying saved session transcript...[/bold cyan]")
        for line in lines:
            self.console.print(line)

    def _handle_team_command(self, argument: str) -> None:
        value = argument.strip().lower()
        if not value:
            self._say(f"team_mode={self.team_mode}")
            return
        if value not in {"auto", "on", "off"}:
            self._say("Use `/team auto`, `/team on`, or `/team off`.")
            return
        self.team_mode = value
        self._say(f"team_mode set to {self.team_mode}")

    def _summarize_text(self, text: str, limit: int = 120) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."
