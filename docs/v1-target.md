# V1 Target

## Goal

Deliver a local CLI that can orchestrate a first-pass cross-vendor coding workflow.

## User Outcome

A user can provide a requirement and get:

- an architect plan
- a frontend worker response
- a backend worker response
- a reviewer verdict
- saved artifacts for inspection

## Acceptance Criteria

- Load workflow configuration from YAML
- Support at least four roles: architect, frontend, backend, reviewer
- Route model calls through one gateway abstraction
- Support mock mode for local development without external keys
- Validate live provider readiness from config and environment variables
- Support optional isolated Git worktrees for worker outputs
- Provide a local MCP server with project and run tools
- Support saved chat sessions and session resume
- Expose team-mode skills and safe coordination writes
- Save each run as `run.json` and `summary.md`
- Provide visible progress tracking in the repository

## Deferred After V1

- MCP tool execution
- Git worktree integration
- automated code patch application
- contract tests
- editor or desktop UI
