# Multi-Agent Orchestrator

CLI-first orchestration system for cross-vendor coding agents.

## Goal

Build a local-first engine that can:

- accept a product or coding request
- generate an execution plan and shared contract
- dispatch frontend and backend work to different model providers
- review, repair, and integrate results
- keep a full audit trail for every run

## First Version Scope

Version 1 focuses on a local CLI workflow:

1. Parse a request into a plan
2. Create structured worker tasks
3. Call different models through a provider gateway
4. Run review and repair loops
5. Store outputs and traces locally

## Project Docs

- `docs/architecture-baseline.md`: fixed architecture and iteration rules
- `docs/v1-target.md`: version 1 goal and acceptance criteria
- `docs/progress.md`: visible delivery checklist

## Useful Commands

```powershell
mao doctor
mao doctor --config configs/live.multi-provider.example.yaml
mao goals
mao status
mao validate --config configs/live.multi-provider.example.yaml
mao roadmap
mao run "Build a task tracker with dashboard" --config configs/local.example.yaml --mock
mao run "Build a task tracker with dashboard" --config configs/local.example.yaml --mock --with-worktrees
mao mcp-serve --transport stdio
mao mcp-serve --transport streamable-http --host 127.0.0.1 --port 8000
```

## Current Building Blocks

The project reuses existing components instead of rebuilding them:

- `LiteLLM` for multi-provider model access
- `MCP Python SDK` for the local MCP server
- system `git` for worktree isolation
- `Typer` and `Rich` for the CLI
- `Pydantic` for configs and run records

## Current Safety Guardrails

- MCP-triggered workflow execution stays in mock mode
- Config paths used by CLI and MCP must stay inside the project root
- Run ids are validated before reading artifacts
- Requirement and defect text are length-bounded before execution and storage

## Development

Create a virtual environment and install the project in editable mode.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

Run the CLI:

```powershell
mao --help
mao doctor
```

Run tests:

```powershell
pytest
```
