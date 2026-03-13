# Multi-Agent Orchestrator

CLI-first orchestration system for cross-vendor coding agents.

## Languages

- Simplified Chinese: [README.zh-CN.md](E:\Ai\multi-agent-orchestrator\README.zh-CN.md)
- Korean: [README.ko-KR.md](E:\Ai\multi-agent-orchestrator\README.ko-KR.md)

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
- `docs/team-mode.md`: current team roles, skill support, and guardrails

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
mao chat --mock
mao chat --mock --with-worktrees
mao skills import-local
mao skills list
mao skills show mcp-builder
mao mcp import-local
mao mcp list
mao mcp show mao_mcp
mao policy show
mao mcp-serve --transport stdio
mao mcp-serve --transport streamable-http --host 127.0.0.1 --port 8000
```

## Chat Mode

`mao chat` provides an interactive shell over the current workflow.

- Enter a requirement to trigger one workflow run
- Watch workflow stage updates in real time during chat execution
- Type `/` and use `Tab` in a real terminal to complete slash commands
- Use `/help` to see commands and their purpose
- Use `/status`, `/doctor`, `/mode`, `/history`, `/context`, `/skills`, `/last`, and `/exit` during a session
- Use `/resume` to choose and restore a saved session from inside chat
- Use `/queue`, `/pick <n>`, `/review`, `/approve`, `/reject`, and `/defer` to work through approval items
- Use `--resume-latest` or `--session-id <id>` to continue a saved session

## Live Providers

Live mode supports both:

- direct official provider APIs
- OpenAI-compatible proxies or routed gateways via `base_url`

Provider configuration can reference:

- `api_key_env`
- `base_url`
- `extra_headers`

## Capability Registry

Local discovery can be imported into MAO's own registry:

- `mao skills import-local`
- `mao mcp import-local`

Operational listing and inspection should use the registry:

- `mao skills list`
- `mao skills show <name>`
- `mao mcp list`
- `mao mcp show <server>`
- `mao policy show`

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
