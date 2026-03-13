# Architecture Layers

## Overview

MAO currently follows a layered CLI-first architecture. The system is still single-repo and single-process by design, but the internal layers are already separated enough to evolve into services later.

## Layer Diagram

```text
User / Operator
  |
  v
Chat CLI / Commands
  |
  v
Session Layer
  - session memory
  - task memory
  - review memory
  - approval queue
  - session resume
  |
  v
Orchestrator Layer
  - architect / frontend / backend / reviewer flow
  - repair loop
  - ownership checks
  - approval decisions
  |
  +----------------------+
  |                      |
  v                      v
Capability Layer         Integration Layer
  - provider config        - integration worktree
  - skill registry         - merge candidates
  - MCP registry           - shared file actor rules
  - capability policy      - apply / queue / review
  |
  v
Provider Layer
  - OpenAI
  - Anthropic
  - Gemini
  - OpenRouter / base_url gateways
  |
  v
External Model APIs
```

## Current Modules

- `chat.py`
  Interactive operator shell.
- `sessions.py`
  Session state, queue state, layered memory.
- `orchestrator.py`
  Main workflow engine and enforcement logic.
- `registry.py`
  Unified capability registry for skills and MCP servers.
- `providers.py`
  Model gateway and provider invocation.
- `gitops.py`
  Worktree creation and proposal apply helpers.
- `mergeflow.py`
  Merge candidate persistence.

## Why The Repo Still Looks Compact

- MAO is still in a CLI-first stage.
- Several concerns are modularized in code, but not split into standalone services yet.
- This keeps iteration speed high while preserving upgrade paths for future service separation.

## Likely Future Splits

- `approval/`
- `integration/`
- `capabilities/`
- `storage/`
- `ui/`
- `services/`

These should only split out when the boundaries are stable enough to justify the operational overhead.
