import json
import subprocess
from pathlib import Path
from uuid import uuid4


import yaml
from typer.testing import CliRunner

from mao_cli.main import app
from mao_cli.core.models import AgentExchange, WorkflowEvent
from mao_cli.gitops import create_worker_worktrees
from mao_cli.orchestrator import execute_workflow, parse_integration_report, parse_review_verdict, _evaluate_ownership



def test_status_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Mock multi-agent flow" in result.stdout


def test_run_command_creates_artifacts(tmp_path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "run",
            "Build a task tracker",
            "--config",
            "configs/local.example.yaml",
            "--output-dir",
            str(tmp_path),
            "--mock",
        ],
    )

    assert result.exit_code == 0
    run_dirs = [item for item in tmp_path.iterdir() if item.is_dir()]
    assert len(run_dirs) == 1

    run_json = run_dirs[0] / "run.json"
    summary = run_dirs[0] / "summary.md"
    payload = json.loads(run_json.read_text(encoding="utf-8"))
    integration_payload = json.loads((run_dirs[0] / "integration.json").read_text(encoding="utf-8"))

    assert summary.exists()
    assert payload["verdicts"][-1]["approved"] is True
    assert payload["verdicts"][0]["defects"][0]["owner"] == "frontend"
    assert payload["plan"]["frontend_task"]["allowed_paths"]
    assert payload["plan"]["backend_task"]["restricted_paths"]
    frontend_exchange = next(item for item in payload["exchanges"] if item["role"] == "frontend")
    assert frontend_exchange["proposed_paths"]

    # Integration artifacts should preserve legacy fields and include structured reports.
    assert "decisions" in integration_payload
    assert "reports" in integration_payload
    assert len(integration_payload["reports"]) == len(payload["verdicts"])


def test_validate_command_fails_when_live_env_missing() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "validate",
            "--config",
            "configs/live.multi-provider.example.yaml",
        ],
    )

    assert result.exit_code == 1
    assert "Missing environment variable" in result.stdout


def test_parse_integration_report_parses_issue_and_binding() -> None:
    report = parse_integration_report(
        "\n".join(
            [
                "INTEGRATION_REPORT:",
                "ROUND: 1",
                "STATUS: needs_changes",
                "SUMMARY: Endpoint mismatch.",
                "",
                "KEY_FINDINGS:",
                "- FE uses /a while BE uses /b",
                "",
                "BINDING:",
                "ID: my-binding",
                "FRONTEND: GET /a",
                "BACKEND: GET /b",
                "REQUEST_FIELDS: a,b",
                "RESPONSE_FIELDS: x,y",
                "MATCH: no",
                "NOTES: fix path",
                "",
                "ISSUE:",
                "ID: my-issue",
                "OWNER: frontend",
                "SEVERITY: high",
                "TITLE: Bad path",
                "SUMMARY: mismatch",
                "ACTION: update frontend",
                "",
                "OPEN_QUESTIONS:",
                "- none",
                "",
                "FILE_TARGETS:",
                "- shared-contracts/x.json",
            ]
        ),
        round_index=1,
        model="mock/integration",
    )

    assert report is not None
    assert report.round_index == 1
    assert report.status == "needs_changes"
    assert report.summary == "Endpoint mismatch."
    assert report.key_findings
    assert len(report.bindings) == 1
    assert report.bindings[0].binding_id == "my-binding"
    assert report.bindings[0].match is False
    assert len(report.issues) == 1
    assert report.issues[0].defect_id == "my-issue"
    assert report.issues[0].owner == "frontend"


def test_parse_review_verdict_with_structured_defect() -> None:
    verdict = parse_review_verdict(
        "\n".join(
            [
                "APPROVED: no",
                "SUMMARY: Frontend and backend endpoint names are inconsistent.",
                "DEFECT:",
                "ID: api-path-mismatch",
                "OWNER: frontend",
                "SEVERITY: high",
                "TITLE: API path mismatch",
                "SUMMARY: Frontend uses /api/task-items while backend exposes /api/tasks.",
                "ACTION: Change the frontend integration to /api/tasks.",
            ]
        )
    )

    assert verdict.approved is False
    assert len(verdict.defects) == 1
    assert verdict.defects[0].owner == "frontend"
    assert "Change the frontend integration" in verdict.frontend_action


def test_create_worker_worktrees(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)

    workspace_root = tmp_path / "worktrees"
    workspaces = create_worker_worktrees(
        repository_root=repo,
        workspace_root=workspace_root,
        run_id="testrun",
        roles=["frontend", "backend"],
    )

    assert len(workspaces) == 2
    assert (workspace_root / "testrun" / "frontend").exists()
    assert (workspace_root / "testrun" / "backend").exists()


def test_run_command_creates_worktrees(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "run",
            "Build a task tracker",
            "--config",
            "configs/local.example.yaml",
            "--output-dir",
            str(tmp_path),
            "--mock",
            "--with-worktrees",
        ],
    )

    assert result.exit_code == 0
    run_dirs = [item for item in tmp_path.iterdir() if item.is_dir()]
    payload = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert len(payload["workspaces"]) == 2
    for workspace in payload["workspaces"]:
        assert Path(workspace["path"]).exists()
        assert Path(workspace["note_path"]).exists()


def test_chat_runs_workflow(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "chat",
            "--mock",
            "--output-dir",
            str(tmp_path),
        ],
        input="Build a task tracker\n/exit\n",
    )

    assert result.exit_code == 0
    assert "Running workflow..." in result.stdout
    assert "architect planning" in result.stdout
    assert "reviewer approved" in result.stdout
    assert "Run artifacts saved to:" in result.stdout


def test_chat_export_command_writes_markdown(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "chat",
            "--mock",
            "--output-dir",
            str(tmp_path),
        ],
        input="/export\n/exit\n",
    )

    assert result.exit_code == 0
    assert "exported=" in result.stdout
    exported_line = next(line for line in result.stdout.splitlines() if "exported=" in line)
    exported_path = Path(exported_line.split("exported=", 1)[1].strip())
    assert exported_path.exists()
    text = exported_path.read_text(encoding="utf-8")
    assert "## Transcript" in text
    assert "assistant> exported=" in text


def test_execute_workflow_emits_events(tmp_path: Path) -> None:
    from mao_cli.config import load_config

    config = load_config(Path("configs/local.example.yaml"))
    events: list[WorkflowEvent] = []
    execute_workflow(
        requirement="Build a task tracker",
        config=config,
        output_dir=tmp_path,
        repository_root=Path("."),
        force_mock=True,
        with_worktrees=False,
        event_handler=events.append,
    )

    event_types = [event.event_type for event in events]
    assert "workflow_started" in event_types
    assert "architect_started" in event_types
    assert "frontend_started" in event_types
    assert "backend_started" in event_types
    assert "integration_completed" in event_types
    assert "review_completed" in event_types
    assert event_types[-1] == "workflow_completed"


def test_tool_protocol_parser_parses_tool_call() -> None:
    from mao_cli.tool_runtime import parse_tool_calls

    calls = parse_tool_calls(
        "\n".join(
            [
                "Some preface.",
                "TOOL_CALL:",
                "TYPE: mcp",
                "NAME: mao_mcp.mao_project_status",
                "ARGS_JSON: {\"params\": {}}",
                "END_TOOL_CALL",
            ]
        )
    )

    assert len(calls) == 1
    assert calls[0].call_type == "mcp"
    assert calls[0].server == "mao_mcp"
    assert calls[0].tool == "mao_project_status"
    assert calls[0].args == {"params": {}}


def test_skill_bind_persists_to_registry(tmp_path: Path) -> None:
    from mao_cli.registry import save_skill_registry, load_skill_registry, bind_skill_to_mcp, SkillRecord

    runtime_root = "runtime"
    project_root = tmp_path

    save_skill_registry(
        project_root,
        runtime_root,
        [SkillRecord(name="pdf", description="PDF helper", path="/tmp/SKILL.md", source="test")],
    )
    bind_skill_to_mcp(project_root, runtime_root, skill="pdf", server="mao_mcp", tool="mao_read_project_doc")

    records = load_skill_registry(project_root, runtime_root)
    record = next(item for item in records if item.name == "pdf")
    assert record.mcp_server == "mao_mcp"
    assert record.mcp_tool == "mao_read_project_doc"


def test_import_local_mcp_merges_without_overwriting_grants(tmp_path: Path) -> None:
    from mao_cli.registry import (
        MCPServerRecord,
        MCPToolRecord,
        import_local_mcp,
        load_mcp_registry,
        save_mcp_registry,
    )

    project_root = tmp_path
    runtime_root = "runtime"

    existing = [
        MCPServerRecord(
            name="dameng_mcp",
            transport="stdio",
            command="python",
            args=["-m", "dameng_mcp"],
            source="manual",
            enabled=True,
            roles=["backend"],
            models=["mock/backend"],
            tools=[MCPToolRecord(name="t1", description="")],
        )
    ]
    save_mcp_registry(project_root, runtime_root, existing)

    # Provide a project manifest that re-discovers the same server.
    (project_root / ".mcp.json").write_text(
        json.dumps(
            {
                "servers": {
                    "dameng_mcp": {"transport": "stdio", "command": "python", "args": ["-m", "dameng_mcp"]}
                }
            }
        ),
        encoding="utf-8",
    )

    import_local_mcp(project_root, runtime_root)
    records = load_mcp_registry(project_root, runtime_root)
    record = next(item for item in records if item.name.lower() == "dameng_mcp")

    # Grants / allowlists should be preserved.
    assert record.roles == ["backend"]
    assert record.models == ["mock/backend"]

    # Existing tool grants should be preserved.
    assert [tool.name for tool in record.tools] == ["t1"]


def test_import_local_mcp_merges_in_new_builtin_tools(tmp_path: Path) -> None:
    from mao_cli.registry import MCPServerRecord, MCPToolRecord, import_local_mcp, load_mcp_registry, save_mcp_registry

    project_root = tmp_path
    runtime_root = "runtime"

    # Existing registry has mao_mcp but with an older tool list.
    save_mcp_registry(
        project_root,
        runtime_root,
        [
            MCPServerRecord(
                name="mao_mcp",
                transport="stdio",
                command="python",
                args=["-m", "mao_cli.main", "mcp-serve", "--transport", "stdio"],
                source="manual",
                enabled=True,
                tools=[MCPToolRecord(name="mao_project_status", description="")],
            )
        ],
    )

    import_local_mcp(project_root, runtime_root)
    records = load_mcp_registry(project_root, runtime_root)
    record = next(item for item in records if item.name.lower() == "mao_mcp")

    # New built-in tools should be appended without removing existing ones.
    tool_names = [tool.name for tool in record.tools]
    assert "mao_project_status" in tool_names
    assert "mao_list_mcp_servers" in tool_names
    assert "mao_read_mcp_server" in tool_names

    # New built-in server record should also exist.
    fs_record = next(item for item in records if item.name.lower() == "mao_fs")
    assert fs_record.roles == ["architect"]



def test_import_local_mcp_discovers_claude_desktop_servers(tmp_path: Path, monkeypatch) -> None:
    from mao_cli.registry import import_local_mcp, load_mcp_registry

    project_root = tmp_path
    runtime_root = "runtime"

    appdata = tmp_path / "appdata"
    claude_dir = appdata / "Claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    (claude_dir / "claude_desktop_config.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "dameng_mcp": {
                        "command": "python",
                        "args": ["-m", "dameng_mcp"],
                        "env": {"DM_TEST": "1"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("APPDATA", str(appdata))
    # Isolate from real ~/.claude/mcp-servers/ on this machine.
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir(exist_ok=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    import_local_mcp(project_root, runtime_root)
    records = load_mcp_registry(project_root, runtime_root)
    record = next(item for item in records if item.name.lower() == "dameng_mcp")

    assert record.transport == "stdio"
    assert record.command == "python"
    assert record.args == ["-m", "dameng_mcp"]
    assert record.env.get("DM_TEST") == "1"




def test_import_local_mcp_tool_probing_populates_registry(tmp_path: Path, monkeypatch) -> None:
    from mao_cli.registry import import_local_mcp, load_mcp_registry

    project_root = tmp_path
    runtime_root = "runtime"

    (project_root / ".mcp.json").write_text(
        json.dumps({"servers": {"dameng_mcp": {"transport": "stdio", "command": "python", "args": ["-m", "dameng_mcp"]}}}),
        encoding="utf-8",
    )

    class _FakeTool:
        def __init__(self, name: str, description: str = ""):
            self.name = name
            self.description = description

    import mao_cli.mcp_client as mcp_client

    monkeypatch.setattr(
        mcp_client,
        "list_mcp_tools_sync",
        lambda _record: [_FakeTool("query", "Run query"), _FakeTool("describe", "Describe table")],
    )

    import_local_mcp(project_root, runtime_root)
    records = load_mcp_registry(project_root, runtime_root)
    record = next(item for item in records if item.name.lower() == "dameng_mcp")
    assert [tool.name for tool in record.tools] == ["query", "describe"]



def test_discover_mcp_from_claude_code_mcp_servers_dir(tmp_path: Path, monkeypatch) -> None:
    from mao_cli.registry import _discover_mcp_from_claude_code_dir

    fake_home = tmp_path / "fakehome"
    mcp_dir = fake_home / ".claude" / "mcp-servers"
    mcp_dir.mkdir(parents=True)
    (mcp_dir / "dameng_mcp.py").write_text("# fake mcp server", encoding="utf-8")
    (mcp_dir / "another_mcp.py").write_text("# another", encoding="utf-8")
    (mcp_dir / "_private.py").write_text("# ignored", encoding="utf-8")
    (mcp_dir / "not_python.txt").write_text("ignored", encoding="utf-8")

    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    records = _discover_mcp_from_claude_code_dir()
    names = [r.name for r in records]

    assert "dameng_mcp" in names
    assert "another_mcp" in names
    assert "_private" not in names
    assert "not_python" not in names

    dameng = next(r for r in records if r.name == "dameng_mcp")
    assert dameng.transport == "stdio"
    assert dameng.source == "claude-code-mcp-servers"
    assert str(mcp_dir / "dameng_mcp.py") in " ".join(dameng.args)


def test_discover_mcp_from_claude_code_settings_json(tmp_path: Path, monkeypatch) -> None:
    from mao_cli.registry import _discover_mcp_from_claude_code_dir

    fake_home = tmp_path / "fakehome"
    claude_dir = fake_home / ".claude"
    claude_dir.mkdir(parents=True)

    (claude_dir / "settings.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "my_mcp": {"command": "python", "args": ["-m", "my_mcp"], "env": {"KEY": "val"}}
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    records = _discover_mcp_from_claude_code_dir()
    assert len(records) == 1
    assert records[0].name == "my_mcp"
    assert records[0].source == "claude-code-settings"
    assert records[0].env == {"KEY": "val"}


def test_architect_bypass_registry_allowlists(tmp_path: Path) -> None:
    from mao_cli.registry import (
        MCPServerRecord,
        MCPToolRecord,
        SkillRecord,
        filter_mcp_servers_for,
        filter_skills_for,
        save_mcp_registry,
        save_skill_registry,
    )

    project_root = tmp_path
    runtime_root = "runtime"

    save_skill_registry(
        project_root,
        runtime_root,
        [
            SkillRecord(
                name="restricted_skill",
                description="x",
                path="/tmp/x",
                source="test",
                enabled=True,
                roles=["backend"],
                models=["mock/backend"],
            )
        ],
    )

    save_mcp_registry(
        project_root,
        runtime_root,
        [
            MCPServerRecord(
                name="restricted_mcp",
                transport="stdio",
                command="python",
                args=["-m", "restricted"],
                source="test",
                enabled=True,
                roles=["backend"],
                models=["mock/backend"],
                tools=[MCPToolRecord(name="t1", description="")],
            )
        ],
    )

    # Non-architect is restricted.
    assert not filter_skills_for(project_root, runtime_root, role="frontend", model="mock/frontend")
    assert not filter_mcp_servers_for(project_root, runtime_root, role="frontend", model="mock/frontend")

    # Architect bypasses allowlists but still requires enabled=true.
    skills = filter_skills_for(project_root, runtime_root, role="architect", model="mock/architect")
    mcps = filter_mcp_servers_for(project_root, runtime_root, role="architect", model="mock/architect")
    assert [s.name for s in skills] == ["restricted_skill"]
    assert [m.name for m in mcps] == ["restricted_mcp"]



def test_ownership_enforcement_detects_conflicts() -> None:
    from mao_cli.orchestrator import build_architect_plan
    from mao_cli.config import load_config

    plan = build_architect_plan("Build a task tracker")
    config = load_config(Path("configs/local.example.yaml"))
    frontend_exchange = AgentExchange(
        role="frontend",
        model="mock/frontend",
        prompt="",
        response="",
        proposed_paths=["shared-contracts/tasks.schema.json", "frontend/dashboard.tsx"],
    )
    backend_exchange = AgentExchange(
        role="backend",
        model="mock/backend",
        prompt="",
        response="",
        proposed_paths=["shared-contracts/tasks.schema.json", "backend/tasks_api.py"],
    )

    defects, notes = _evaluate_ownership(
        config=config,
        frontend_task=plan.frontend_task,
        backend_task=plan.backend_task,
        frontend_exchange=frontend_exchange,
        backend_exchange=backend_exchange,
    )

    assert defects
    assert any(defect.owner == "shared" for defect in defects)
    assert any("integration" in defect.action.lower() for defect in defects)
    assert notes


def test_chat_history_and_context_with_resumable_session(tmp_path: Path) -> None:
    config_path = Path(f"runtime/test-chat-config-{uuid4().hex}.yaml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "project_name": "multi-agent-orchestrator",
                "runtime_root": str(runtime_root.resolve()),
                "artifacts_root": str(artifacts_root.resolve()),
                "workflow": {"max_repair_rounds": 1},
                "providers": {
                    "architect": {"adapter": "mock", "model": "mock/architect"},
                    "frontend": {"adapter": "mock", "model": "mock/frontend"},
                    "backend": {"adapter": "mock", "model": "mock/backend"},
                    "reviewer": {"adapter": "mock", "model": "mock/reviewer"},
                },
            }
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["chat", "--mock", "--config", str(config_path)],
        input="Build a task tracker\n/history\n/context\n/exit\n",
    )

    assert result.exit_code == 0
    assert "Session History" in result.stdout
    assert "Conversation context from recent turns:" in result.stdout


def test_chat_resume_command_restores_session(tmp_path: Path) -> None:
    config_path = Path(f"runtime/test-resume-config-{uuid4().hex}.yaml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "project_name": "multi-agent-orchestrator",
                "runtime_root": str(runtime_root.resolve()),
                "artifacts_root": str(artifacts_root.resolve()),
                "workflow": {"max_repair_rounds": 1},
                "providers": {
                    "architect": {"adapter": "mock", "model": "mock/architect"},
                    "frontend": {"adapter": "mock", "model": "mock/frontend"},
                    "backend": {"adapter": "mock", "model": "mock/backend"},
                    "reviewer": {"adapter": "mock", "model": "mock/reviewer"},
                },
            }
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    first = runner.invoke(
        app,
        ["chat", "--mock", "--config", str(config_path)],
        input="Build a task tracker\n/exit\n",
    )
    assert first.exit_code == 0

    second = runner.invoke(
        app,
        ["chat", "--mock", "--config", str(config_path), "--resume-latest"],
        input="/resume\n1\n/last\n/exit\n",
    )
    assert second.exit_code == 0
    assert "Saved Sessions" in second.stdout
    assert "Resumed session" in second.stdout
    assert "user> Build a task tracker" in second.stdout
    assert "last_run=" in second.stdout

    # Ensure per-role long-lived memories are persisted into the session JSON.
    sessions_dir = runtime_root / "sessions"
    session_files = list(sessions_dir.glob("*.json"))
    assert session_files
    payload = json.loads(session_files[0].read_text(encoding="utf-8"))
    assert "role_memories" in payload
    assert isinstance(payload["role_memories"], dict)
    # Mock provider should have produced at least one role memory after the workflow.
    assert any(payload["role_memories"].get(role, "").strip() for role in ("frontend", "backend", "integration", "reviewer"))


def test_chat_approval_queue_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["chat", "--mock"],
        input="Build a task tracker\n/queue\n/pick 1\nd\n/queue\n/pick 2\ny\n/exit\n",
    )

    assert result.exit_code == 0
    assert "approval_queue=" in result.stdout
    assert "Approval Queue" in result.stdout
    assert "approval_item=" in result.stdout
    assert "deferred:" in result.stdout
    assert "applied_to=" in result.stdout


def test_chat_auto_team_mode_routes_simple_prompt_to_primary_model() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["chat", "--mock"],
        input="你好\n/exit\n",
    )

    assert result.exit_code == 0
    assert "calling architect..." in result.stdout
    # Single-model mode prints the full response (no "architect summary:" prefix).
    assert "frontend calling frontend..." not in result.stdout


def test_chat_auto_team_mode_keeps_direct_fs_request_single_model() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["chat", "--mock"],
        input="创建 tmp/live-test.txt 写入 hello live\n/exit\n",
    )

    assert result.exit_code == 0
    assert "calling architect..." in result.stdout
    assert "frontend calling frontend..." not in result.stdout
    assert "backend calling backend..." not in result.stdout


def test_chat_team_on_forces_team_workflow() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["chat", "--mock"],
        input="/team on\n你好\n/exit\n",
    )

    assert result.exit_code == 0
    assert "team_mode set to on" in result.stdout
    assert "frontend calling frontend..." in result.stdout


def test_chat_member_toggle_disables_backend() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["chat", "--mock"],
        input="/member off backend\nBuild a task tracker\n/exit\n",
    )

    assert result.exit_code == 0
    assert "member backend set to False" in result.stdout
    assert "frontend calling frontend..." in result.stdout
    assert "backend calling backend..." not in result.stdout


def test_chat_live_preflight_fails_cleanly(tmp_path: Path) -> None:
    config_path = Path(f"runtime/test-live-config-{uuid4().hex}.yaml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "project_name": "multi-agent-orchestrator",
                "runtime_root": str(runtime_root.resolve()),
                "artifacts_root": str(artifacts_root.resolve()),
                "workflow": {"max_repair_rounds": 1},
                "providers": {
                    "architect": {"adapter": "openai", "model": "openai/gpt-5.4", "api_key_env": "OPENAI_API_KEY"},
                    "frontend": {"adapter": "gemini", "model": "gemini/gemini-2.5-pro", "api_key_env": "GEMINI_API_KEY"},
                    "backend": {"adapter": "anthropic", "model": "anthropic/claude-sonnet-4-20250514", "api_key_env": "ANTHROPIC_API_KEY"},
                    "reviewer": {"adapter": "openrouter", "model": "openrouter/openai/gpt-4.1", "api_key_env": "OPENROUTER_API_KEY"},
                },
            }
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["chat", "--live", "--config", str(config_path)],
        input="/exit\n",
    )

    assert result.exit_code != 0
    assert "Live mode preflight failed." in result.output
