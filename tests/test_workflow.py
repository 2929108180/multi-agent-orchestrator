import json

from typer.testing import CliRunner

from mao_cli.main import app


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
