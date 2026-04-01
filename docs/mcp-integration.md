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
- `mao_list_mcp_servers`
  List registered MCP servers (registry introspection).
- `mao_read_mcp_server`
  Read one registered MCP server record.
- `mao_write_team_note`
  Append a safe coordination note under `runtime/team`.
- `mao_write_session_note`
  Append a note to a saved session.

## File System MCP (mao_fs)

`mao_fs` is an **architect-only** MCP server record (controlled by the registry allowlist). It enables single-model runs to perform file system CRUD inside the project root.

Tools:

- `mao_fs_list_dir`
- `mao_fs_read_text`
- `mao_fs_write_text` (overwrite requires `overwrite=true` + `confirm="YES"`)
- `mao_fs_mkdir`
- `mao_fs_delete_file` (requires `confirm="DELETE"`)
- `mao_fs_delete_dir` (requires `confirm="DELETE"`; supports `recursive=true`)

Guardrails:

- Project-root sandbox only
- Reject any path inside `.git/`
- Refuse deleting the project root

## Transport

- `stdio`
  Best for local MCP clients launched by another process.
- `streamable-http`
  Best for browser-based clients, inspectors, or manual local testing.

## Notes

- The current MCP slice is intentionally local-first.
- It does not replace the CLI.
- MCP tools that read sessions/skills/runs accept an optional `config_path` to ensure consistent `runtime_root` and `artifacts_root` resolution.
- The CLI can call registered MCP tools via `mao mcp call`.
- Team workflow runs and single-model chat runs can also call MCP tools via the cross-provider `TOOL_CALL` text protocol (with registry allowlists).
- It creates a stable seam for team coordination, local memory, and file tools.

## MCP Auto-Discovery Sources

`mao mcp import-local` scans the following locations (in order):

1. **Built-in**: `mao_mcp` + `mao_fs` (always present)
2. **Project manifest**: `<project_root>/.mcp.json`
3. **Claude Desktop**: `%APPDATA%/Claude/claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
4. **Claude Code settings**: `~/.claude/settings*.json` → `mcpServers` key
5. **Claude Code MCP servers directory**: `~/.claude/mcp-servers/*.py` — each `.py` file is registered as a stdio MCP server (server name = filename without `.py`)

All sources are merged non-destructively: existing grants (roles/models/enabled) are preserved.
