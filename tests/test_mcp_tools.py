from mao_cli.mcp_tools import list_runs, project_status_text, read_project_doc, trigger_mock_workflow


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
    runs = list_runs(limit=5)
    assert runs
