from typer.testing import CliRunner

from mao_cli.main import app


def test_doctor_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "--mock"])

    assert result.exit_code == 0
    assert "ready for local development" in result.stdout
    assert "architect" in result.stdout
    assert "mock" in result.stdout


def test_chat_exit_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["chat", "--mock"], input="/exit\n")

    assert result.exit_code == 0
    assert "Chat closed." in result.stdout


def test_chat_prefix_command_resolves() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["chat", "--mock"], input="/sta\n/exit\n")

    assert result.exit_code == 0
    assert "config=" in result.stdout
