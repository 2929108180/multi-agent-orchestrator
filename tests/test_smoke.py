from typer.testing import CliRunner

from mao_cli.main import app


def test_doctor_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "ready for local development" in result.stdout
