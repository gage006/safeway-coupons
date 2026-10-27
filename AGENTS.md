# Project instructions

- Always commit and push project changes to `main` unless the user explicitly requests a different branch.
- After every push, monitor all CI runs for the pushed commit until they finish. Fix failures, push the corrections to `main`, and repeat until CI passes. Report any blocker that cannot be resolved.
- Use the formatter version pinned in `.pre-commit-config.yaml` when checking formatting locally.
