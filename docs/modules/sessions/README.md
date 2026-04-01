# Sessions Module

## Current Capabilities

- saved sessions
- resume latest
- resume by id
- transcript replay (on resume)
- layered memory
- export session transcript to markdown
  - CLI: `mao session export <session_id> [-o output.md] [-c config.yaml]`
  - Chat: `/export [relative/path.md]`

## Memory Layers

- session memory (turns/transcript)
- task memory (recent turn summaries per role)
- review memory (recent verdict summaries)
- role memories (long-lived per-role bounded summaries persisted in session JSON)

## Next Improvements

- full transcript fidelity replay
- session import
- better session search
