import json
import subprocess
from pathlib import Path

import yaml
from typer.testing import CliRunner

from mao_cli.main import app
from mao_cli.core.models import AgentExchange, WorkflowEvent
from mao_cli.gitops import create_worker_worktrees
from mao_cli.orchestrator import execute_workflow, parse_review_verdict, _evaluate_ownership


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

    assert summary.exists()
    assert payload["verdicts"][-1]["approved"] is True
    assert payload["verdicts"][0]["defects"][0]["owner"] == "frontend"
    assert payload["plan"]["frontend_task"]["allowed_paths"]
    assert payload["plan"]["backend_task"]["restricted_paths"]
    assert payload["exchanges"][1]["proposed_paths"]


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


def test_execute_workflow_emits_events(tmp_path: Path) -> None:
    from mao_cli.config import load_config

    config = load_config(Path("E:/Ai/multi-agent-orchestrator/configs/local.example.yaml"))
    events: list[WorkflowEvent] = []
    execute_workflow(
        requirement="Build a task tracker",
        config=config,
        output_dir=tmp_path,
        repository_root=Path("E:/Ai/multi-agent-orchestrator"),
        force_mock=True,
        with_worktrees=False,
        event_handler=events.append,
    )

    event_types = [event.event_type for event in events]
    assert "workflow_started" in event_types
    assert "architect_started" in event_types
    assert "frontend_started" in event_types
    assert "backend_started" in event_types
    assert "review_completed" in event_types
    assert event_types[-1] == "workflow_completed"


def test_ownership_enforcement_detects_conflicts() -> None:
    from mao_cli.orchestrator import build_architect_plan
    from mao_cli.config import load_config

    plan = build_architect_plan("Build a task tracker")
    config = load_config(Path("E:/Ai/multi-agent-orchestrator/configs/local.example.yaml"))
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
    config_path = Path("E:/Ai/multi-agent-orchestrator/runtime/test-chat-config.yaml")
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "project_name": "multi-agent-orchestrator",
                "runtime_root": str((tmp_path / "runtime").resolve()),
                "artifacts_root": str((tmp_path / "artifacts").resolve()),
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
    config_path = Path("E:/Ai/multi-agent-orchestrator/runtime/test-resume-config.yaml")
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "project_name": "multi-agent-orchestrator",
                "runtime_root": str((tmp_path / "runtime").resolve()),
                "artifacts_root": str((tmp_path / "artifacts").resolve()),
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
    assert "architect summary:" in result.stdout
    assert "frontend:" not in result.stdout


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
    config_path = Path("E:/Ai/multi-agent-orchestrator/runtime/test-live-config.yaml")
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "project_name": "multi-agent-orchestrator",
                "runtime_root": str((tmp_path / "runtime").resolve()),
                "artifacts_root": str((tmp_path / "artifacts").resolve()),
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
