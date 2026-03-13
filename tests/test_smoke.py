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


def test_registry_commands() -> None:
    runner = CliRunner()

    imported_skills = runner.invoke(app, ["skills", "import-local"])
    assert imported_skills.exit_code == 0
    assert "imported=" in imported_skills.stdout

    listed_skills = runner.invoke(app, ["skills", "list"])
    assert listed_skills.exit_code == 0
    assert "Skill Registry" in listed_skills.stdout

    imported_mcp = runner.invoke(app, ["mcp", "import-local"])
    assert imported_mcp.exit_code == 0
    assert "Imported MCP Servers" in imported_mcp.stdout

    listed_mcp = runner.invoke(app, ["mcp", "list"])
    assert listed_mcp.exit_code == 0
    assert "MCP Registry" in listed_mcp.stdout

    policy = runner.invoke(app, ["policy", "show"])
    assert policy.exit_code == 0
    assert "Approval" in policy.stdout

    grant_skill = runner.invoke(app, ["skills", "grant", "mcp-builder", "--role", "frontend"])
    assert grant_skill.exit_code == 0
    assert "granted=" in grant_skill.stdout

    register_mcp = runner.invoke(
        app,
        ["mcp", "register", "demo_mcp", "--transport", "streamable-http", "--url", "http://localhost:8123/mcp"],
    )
    assert register_mcp.exit_code == 0
    assert "registered=demo_mcp" in register_mcp.stdout
