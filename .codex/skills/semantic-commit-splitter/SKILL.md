---
name: semantic-commit-splitter
description: Split local repository changes into meaningful, reviewable Git commits based on intent. Use when the user asks to commit changes, prepare commits, divide a large diff, make semantic commits, or decide what should be staged together.
---

# Semantic Commit Splitter

## Overview

Use this skill to convert an unstructured working tree into a small sequence of commits where each commit has one reason to exist and can be reviewed independently.

For detailed grouping criteria, read `references/grouping-rubric.md` when the diff is large, mixed, or ambiguous.

## Workflow

1. Inspect the working tree with `git status --short`, then inspect relevant diffs before deciding groups.
2. Identify intent-level groups, not just file-extension groups.
3. Keep generated artifacts, formatting-only changes, docs, tests, config, and product behavior separate when they can stand alone.
4. Check whether each group builds on a previous group. If so, order commits from foundation to dependent change.
5. Stage only the files or hunks for the current group. Avoid broad `git add .` unless every changed file belongs to that group.
6. Use concise commit messages that describe the intent, not the mechanics.
7. After each commit, re-check `git status --short` before staging the next group.

## Grouping Rules

- Put one conceptual change in one commit.
- Separate scaffolding from behavior when both are present.
- Separate tests from implementation only when the tests are useful as an independent review unit; otherwise keep them with the behavior they verify.
- Keep repository rules, documentation, and generated app code separate if they serve different audiences.
- Never include secrets, large datasets, checkpoints, or local-only artifacts in a commit.
- If a file contains unrelated hunks, use patch staging or ask before committing.

## Output Before Committing

When the user asks for commits but has not specified exact grouping, first provide a short commit plan:

```text
1. <commit subject>
   Files: <paths>
   Reason: <single intent>
```

Then commit in that order if the user has requested implementation through commit. If the user only asked for a plan, stop after the plan.

## Commit Message Style

Use imperative, present-tense subjects:

- `Document Git Archaeologist tuning flow`
- `Add React tuning PoC`
- `Implement SFT data override`
- `Add semantic commit splitting skill`

Avoid vague subjects such as `Update files`, `Fix stuff`, or `Changes`.
