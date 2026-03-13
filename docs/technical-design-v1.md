# Technical Design v1

## Product Direction

The system is a CLI-first orchestration layer for cross-vendor coding agents.
It is designed to coordinate planning, execution, review, and repair across
multiple model providers while keeping a local audit trail.

## Core Principles

- CLI first, GUI later
- Local-first execution and logs
- Structured task contracts, not prompt-only orchestration
- Independent workspaces for each worker
- Machine checks before model-based review

## Planned Modules

- `cli`: command surface for local operation
- `core`: shared models and workflow state
- `providers`: provider adapters and routing
- `orchestrator`: plan, dispatch, review, repair
- `mcp`: tool access layer
- `gitops`: worktree and merge operations
- `storage`: run metadata and event history

## v1 Milestones

1. Establish package layout and local CLI
2. Add run configuration and runtime state storage
3. Implement planner and task spec models
4. Add provider gateway through LiteLLM
5. Add worker execution loop
6. Add review and repair loop
7. Add Git integration
