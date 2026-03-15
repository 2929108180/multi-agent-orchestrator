from mao_cli.mcp_tools import (
    list_available_skills,
    list_runs,
    list_saved_sessions,
    project_status_text,
    read_project_doc,
    trigger_mock_workflow,
    write_team_note,
)
from mao_cli.security import validate_run_id


def test_project_status_text() -> None:
    content = project_status_text()
    assert "V1 Delivery Checklist" in content


def test_read_project_doc() -> None:
    content = read_project_doc("v1-target")
    assert "Acceptance Criteria" in content


def test_trigger_mock_workflow_returns_run() -> None:
    result = trigger_mock_workflow("Build a kanban board")
    assert result.run_id
    assert result.summary_path.endswith("summary.md")
    assert result.approved is True


def test_list_runs_has_recent_item() -> None:
    runs = list_runs(limit=5, config_path="configs/local.example.yaml")
    assert runs


def test_validate_run_id_rejects_path_traversal() -> None:
    try:
        validate_run_id("../bad")
    except ValueError as exc:
        assert "Invalid run id" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid run id")


def test_list_saved_sessions() -> None:
    sessions = list_saved_sessions(limit=5)
    assert isinstance(sessions, list)


def test_list_available_skills() -> None:
    skills = list_available_skills()
    assert isinstance(skills, list)


def test_write_team_note() -> None:
    path = write_team_note("test note from pytest", category="pytest")
    assert path.endswith("pytest.md")
