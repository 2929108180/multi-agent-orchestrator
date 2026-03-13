# Architecture Baseline

## One Layer Fixed

These parts are fixed unless there is a major product reset:

- Product shape: CLI-first orchestration engine for cross-vendor coding agents
- Core flow: Architect -> Workers -> Reviewer -> Repair Loop -> Final Output
- Contract-first execution: tasks, ownership, and acceptance rules must be structured
- Local-first delivery: every run must leave artifacts and traces on disk
- Building blocks: use existing ecosystem pieces before inventing new ones

## Three Layers Iterated

These layers will evolve version by version:

1. Model layer
   Select providers, routing rules, fallback rules, and pricing strategy.
2. Workflow layer
   Improve planning quality, review quality, repair loops, and Git integration.
3. Product layer
   Add editor integration, desktop shell, web console, team controls, and enterprise governance.

## Existing Building Blocks

- `LiteLLM`
  Unified model gateway for multi-vendor inference and routing.
- `MCP`
  Standard tool access layer for files, Git, databases, browsers, and future connectors.
- `Git`
  Source-of-truth integration, worktree isolation, and merge discipline.
- `Pydantic`
  Structured task contracts and workflow state.
- `Typer` + `Rich`
  CLI surface and local operator experience.

## Guardrails

- Do not depend on free-form agent chat as the main protocol.
- Run machine checks before model review whenever tooling exists.
- Keep worker ownership explicit to avoid overwrite conflicts.
- Preserve auditability across every run and every agent exchange.
