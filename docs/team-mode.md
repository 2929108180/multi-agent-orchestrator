# Team Mode

## Goal

Treat the orchestrator as a local AI team instead of a single model shell.

## Current Team Roles

- `architect`
  Plans the delivery slice and the shared contract.
- `frontend`
  Owns frontend and UI-facing paths.
- `backend`
  Owns backend and API-facing paths.
- `reviewer`
  Checks cross-role consistency and routes defects back to the right owner.

## Current Guardrails

- Frontend and backend tasks carry explicit `allowed_paths`.
- Frontend and backend tasks carry explicit `restricted_paths`.
- Shared contract changes are not assigned directly to a worker.
- Git worktrees isolate worker outputs when enabled.

## Skill + MCP Tool Support

- Local skills are discovered from the Codex skills directory when available.
- Skills can be bound to MCP tools (Skill -> MCP indirection) so models can call them during runs.
- Chat mode exposes skills with `/skills`, and binding via `/bind-skill <skill> <server> <tool>`.

## Tool Calling in Team Runs

- Both team workflow runs and single-model chat runs support an iterative tool execution loop.
- Models request tools via a text protocol block (`TOOL_CALL`), MAO executes the tool, then feeds back `TOOL_RESULT` and continues generation.
- Tool availability is filtered by the registry allowlist for the current role/model.
- **Architect bypass:** the `architect` role can always see/call all registered skills and MCP servers (still respects `enabled=false`).

## Supervisor Brief Distribution (No Raw Broadcast)

- Only the architect/supervisor sees the raw user requirement.
- Before dispatching to workers, MAO asks the architect to generate role-specific briefs.
- Workers (frontend/backend/integration/reviewer) receive only their brief + shared contract + constraints, rather than the full raw user input.

## Session Support

- Chat sessions are saved locally.
- Recent turns can be fed back into new workflow runs as conversation context.
- MAO also persists a bounded per-role `Role memory:` (frontend/backend/integration/reviewer) and injects it into future worker prompts.
- Sessions can be resumed by id or by `--resume-latest`.
