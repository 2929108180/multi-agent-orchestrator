# Team Module

## Current Capabilities

- supervisor-led orchestration
- roles: `architect / frontend / backend / integration / reviewer`
- explicit member toggles for `frontend / backend / integration / reviewer`
- explicit team mode control
- member-level enable/disable control
- worker ownership boundaries
- per-role long-lived memory injection (`Role memory:`) into worker prompts

## Current Rules

- user explicit team mode overrides auto mode
- auto mode uses supervisor decision
- members can be individually disabled
- reviewer can remain enabled even when a worker is disabled

## Next Improvements

- dynamic non-coding roles beyond frontend/backend/reviewer
- integration actor as a fully explicit role in config and plans
- team templates by project type
- richer supervisor delegation policies
