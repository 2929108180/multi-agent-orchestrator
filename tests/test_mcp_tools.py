from pathlib import Path
from uuid import uuid4

from mao_cli.mcp_tools import (
    fs_find_paths,
    fs_write_text,
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


def test_fs_write_text_returns_diff_for_new_file() -> None:
    rel = f"runtime/test-create-{uuid4().hex}.txt"
    output = fs_write_text(rel, "hello\nworld\n")
    normalized_rel = rel.replace("/", "\\")
    assert output.startswith(f"create {normalized_rel}\n")
    assert "--- /dev/null" in output
    assert f"+++ b/{normalized_rel}" in output
    assert "+hello" in output
    assert "+world" in output


def test_fs_find_paths_finds_exact_name() -> None:
    rel = f"runtime/find-me-{uuid4().hex}.txt"
    fs_write_text(rel, "hello\n")
    matches = fs_find_paths(Path(rel).name, exact=True, include_files=True, include_dirs=False)
    assert any(item.path.endswith(rel.replace("/", "\\")) or item.path.endswith(rel) for item in matches)


def test_fs_write_text_rejects_ambiguous_bare_filename() -> None:
    rel = f"runtime/nested-{uuid4().hex}/same-name.txt"
    fs_write_text(rel, "hello\n")
    try:
        fs_write_text("same-name.txt", "new content\n")
    except ValueError as exc:
        assert "Ambiguous path" in str(exc)
        assert "Use the exact relative path" in str(exc)
    else:
        raise AssertionError("Expected ValueError for ambiguous bare filename")
