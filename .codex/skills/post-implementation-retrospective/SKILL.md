---
name: post-implementation-retrospective
description: Review a completed implementation session and propose improvements to repository assistance, agent instructions, skills, rules, hooks, docs, or workflow automation. Use after implementation work is done, especially before or after commits, when lessons from the session could improve future development quality or instruction clarity. Ask for approval before editing or creating any support files.
---

# Post Implementation Retrospective

## Overview

Use this skill to turn friction from a completed implementation session into durable repository improvements. The goal is not to keep changing code forever; it is to notice repeatable problems and improve the support system around future work.

## Workflow

1. Gather session evidence.
   - Inspect `git status --short`, recent commits, changed files, and relevant test results.
   - Review the user's explicit instructions from the session when available.
   - Identify what was confusing, repetitive, error-prone, blocked by permissions, or easy to forget.

2. Identify improvement candidates.
   - Skills: create or update when a repeatable workflow needs procedural guidance.
   - `AGENTS.md`: update when repository-wide agent behavior should change.
   - `.codex/rules/`: update when a stable repository rule should be enforced for future agents.
   - Hooks or scripts: propose when a repeatable check can be automated before commit or run.
   - Docs or templates: propose when humans need a clearer runbook or checklist.

3. Decide whether a change is worth proposing.
   - Prefer changes that prevent a repeated mistake, reduce future prompts, clarify approvals, or improve verification.
   - Avoid adding process for one-off issues, personal preference, or speculative future needs.
   - Keep proposed changes small and scoped to the observed session.

4. Ask for approval before mutating support files.
   - Present each proposed edit with target file, reason, expected benefit, and risk.
   - Wait for user approval before editing or creating Skills, `AGENTS.md`, rules, hooks, scripts, or docs.
   - If the user already explicitly requested a specific retrospective change, that request counts as approval for that change only.

5. Implement approved changes.
   - Follow existing repository structure and style.
   - Keep hand-authored files under 500 lines.
   - For new skills, include clear frontmatter triggers and concise body instructions.
   - For hooks or scripts, add tests or a dry-run path when practical.

6. Validate and report.
   - Run `quick_validate.py` for new or changed skills when available.
   - Run relevant tests or static checks for changed scripts or rules when practical.
   - Summarize what changed, what was verified, and what still needs human judgment.

## Retrospective Output Format

When proposing changes, use this compact shape:

```text
Observed friction:
- <what happened>

Proposed improvement:
- <target file or asset>: <change>

Expected benefit:
- <how this improves future development or instruction quality>

Approval needed:
- <specific edits that require user approval>
```

## Guardrails

- Do not edit support files silently.
- Do not add hooks that block commits without explaining the failure mode and bypass path.
- Do not create broad rules from a single ambiguous incident.
- Do not store secrets, private data, large logs, datasets, or model artifacts in retrospective outputs.
- Do not conflate product code fixes with process improvements; commit them separately when both are needed.
