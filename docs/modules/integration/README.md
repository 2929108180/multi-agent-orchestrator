# Integration Module

## Current Capabilities

- integration actor is now an explicit workflow role
- integration worktree apply
- merge candidate generation
- `mao merge list`
- shared file block to integration actor path

## Current Rules

- integration actor runs after frontend/backend and before reviewer
- approved worker-owned files can be applied to integration worktree
- shared files do not apply directly
- merge candidates are stored for later branch integration

## Next Improvements

- target branch merge apply
- explicit shared-file integration actor workflow
- merge reject / merge promote commands
