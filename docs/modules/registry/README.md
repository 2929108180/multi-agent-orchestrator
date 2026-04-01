# Registry Module

## Current Capabilities

- skill registry
- MCP server registry
- local import
- manual registration
- role/model grants

## Current Commands

- `mao skills import-local`
- `mao skills list`
- `mao skills show`
- `mao skills register`
- `mao skills grant`
- `mao skills bind` (skill -> MCP tool)
- `mao mcp import-local` (merge + discovery)
- `mao mcp list`
- `mao mcp show`
- `mao mcp tools`
- `mao mcp register`
- `mao mcp grant`
- `mao mcp call`

## MCP discovery (import-local)

`mao mcp import-local` discovers MCP servers from:

- Project-level manifest: `<project_root>/.mcp.json`
- User-level Claude Desktop config (best-effort):
  - Windows: `%APPDATA%/Claude/claude_desktop_config.json`

Import behavior is **merge** (not overwrite): existing registry entries keep their `enabled` state and any `roles/models/tools` grants/allowlists. Discovered connection details (`transport/command/args/url/env/source`) are refreshed.

After merging, MAO will do a best-effort `list_tools` probe to populate `server.tools` so tool names like `<server>.<tool>` appear in the tool catalog. Probe failures will not block import.

## Next Improvements

- registry remove/disable commands
- capability groups
- more explicit policy UI
- consistent runtime_root/artifacts_root resolution across CLI/MCP
