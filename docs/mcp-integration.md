# MCP Integration

## Goal

Expose the current project state and workflow entry points through a local MCP server.

## Current MCP Tools

- `mao_project_status`
  Read the current progress document.
- `mao_read_project_doc`
  Read one tracked project document by stable name.
- `mao_list_runs`
  List the most recent workflow runs and their approval state.
- `mao_read_run_summary`
  Read the markdown summary for a saved run.
- `mao_trigger_mock_workflow`
  Trigger the local mock workflow and save a new run.
- `mao_list_sessions`
  List saved local chat sessions.
- `mao_read_session`
  Read a saved local chat session.
- `mao_list_skills`
  List discovered local skills for team mode.
- `mao_read_skill`
  Read one discovered skill entry.
- `mao_write_team_note`
  Append a safe coordination note under `runtime/team`.
- `mao_write_session_note`
  Append a note to a saved session.

## Transport

- `stdio`
  Best for local MCP clients launched by another process.
- `streamable-http`
  Best for browser-based clients, inspectors, or manual local testing.

## Notes

- The current MCP slice is intentionally local-first.
- It does not replace the CLI.
- It creates a stable seam for team coordination, local memory, and future Git/file tools.
