# Phase 5 User Acceptance Evaluation

This directory contains deterministic fixtures for human acceptance review. The
records are synthetic and pseudonymous; they contain no private repository
artifacts, personal information, secrets, or live model output.

- `user-acceptance-form.json`: fixed rubric, cases, and release thresholds.
- `sample-evaluations.jsonl`: example completed review records for tests and
  report-builder smoke checks.

Report generation uses only these checked-in files:

```powershell
uv --system-certs run python -m git_archaeologist.evaluation.user_acceptance
```
