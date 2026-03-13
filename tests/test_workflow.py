import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from mao_cli.main import app
from mao_cli.gitops import create_worker_worktrees


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
