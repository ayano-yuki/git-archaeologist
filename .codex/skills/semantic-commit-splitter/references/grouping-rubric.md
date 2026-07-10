# Semantic Commit Grouping Rubric

Use this rubric when a working tree contains mixed changes.

## Strong Split Signals

- Different user-facing outcomes.
- Infrastructure or scaffolding plus product behavior.
- Documentation that describes work separately from the implementation.
- Tests for an existing behavior change plus unrelated test cleanup.
- Generated artifacts mixed with hand-authored source.
- Repository policy changes mixed with application code.

## Keep Together Signals

- A code change and its direct tests.
- A config value and the code that first consumes it.
- A small documentation note required to explain a new command.
- File moves that would be confusing without the corresponding import updates.

## Ordering

1. Repository rules and scaffolding.
2. Shared utilities or config loaders.
3. Product behavior or app code.
4. Tests and validation updates if not bundled with behavior.
5. Documentation and examples.

Prefer commits that leave the repository understandable after every step.
