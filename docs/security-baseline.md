# Security Baseline

## Current Guardrails

- Keep MCP-triggered workflow execution in mock mode only.
- Restrict config paths resolved by CLI and MCP to the project root.
- Validate run ids before loading run artifacts.
- Bound requirement and defect text lengths before execution and persistence.
- Keep repair loop limits enforced by workflow configuration.

## Why These Come First

- They reduce accidental path traversal and unsafe file access.
- They avoid exposing live API keys or costs through MCP-triggered runs.
- They limit prompt and artifact bloat during local development.

## Deferred Hardening

- Tool-level allowlists for future MCP file and git write operations
- Secret redaction in stored run artifacts
- Optional human approval gates for live provider execution
