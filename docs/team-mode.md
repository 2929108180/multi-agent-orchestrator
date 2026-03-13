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

## Skill Support

- Local skills are discovered from the Codex skills directory when available.
- Chat mode exposes them with `/skills`.
- Team context includes the discovered skill inventory for future agent routing.

## Session Support

- Chat sessions are saved locally.
- Recent turns can be fed back into new workflow runs as conversation context.
- Sessions can be resumed by id or by `--resume-latest`.
