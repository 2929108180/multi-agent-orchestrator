# Progress

## Fixed Baseline

- [x] CLI-first direction is fixed
- [x] Core workflow shape is fixed
- [x] Existing building blocks are fixed
- [x] Long-term architecture is written into the repository

## V1 Delivery Checklist

- [x] Bootstrap Python CLI project
- [x] Add local project docs and visible scope
- [x] Add structured configuration models
- [x] Add workflow models for architect, workers, and reviewer
- [x] Add provider gateway abstraction
- [x] Add mock-mode multi-agent workflow
- [x] Add live multi-provider key validation helpers
- [x] Add Git worktree integration
- [x] Add MCP tool integration
- [x] Add structured review-to-repair routing
- [x] Add chat session memory and resume
- [x] Add live chat preflight
- [x] Add local skill discovery for team mode
- [x] Add safe MCP write tools for team notes and session notes
- [x] Add worker ownership metadata to reduce write conflicts
- [ ] Add persistent run index and search

## Security Baseline

- [x] Restrict MCP-triggered execution to mock mode
- [x] Add project-root config path checks
- [x] Add run id validation for artifact reads
- [x] Add bounded requirement and defect text handling

## Current Slice

The current implementation target is:

`chat session -> contextual workflow -> reviewer repair loop -> saved sessions and team tools`
