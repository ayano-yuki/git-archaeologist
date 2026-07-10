---
name: fine-tuning-memory-writer
description: Write repository memory notes for LLM fine-tuning knowledge. Use when fine-tuning lessons, warnings, failures, successful patterns, dataset issues, training configuration findings, evaluation learnings, or beginner explanations should be recorded in .memory/fine-tuning/.
---

# Fine-tuning Memory Writer

## Overview

Use this skill to turn fine-tuning experience into durable repository memory. The note should teach a beginner what happened, why it matters, and how to act next.

Read `references/writing-guide.md` before writing a new memory note.

## Workflow

1. Identify the single lesson to preserve.
2. Check `.memory/fine-tuning/README.md` and existing `.memory/fine-tuning/entries/` notes to avoid duplicates.
3. Create one Markdown file under `.memory/fine-tuning/entries/`.
4. Use the filename format `YYYY-MM-DD-short-title.md`.
5. Follow `.memory/fine-tuning/templates/knowledge-note.md` unless a shorter structure is clearly enough.
6. Explain terms and background for beginners.
7. Separate observed facts from interpretation or advice.
8. Remove secrets, private data, full datasets, checkpoints, and long logs.

## Required Sections

Each memory note should include:

- `Summary`
- `Context`
- `What Happened`
- `Beginner Explanation`
- `Why It Matters`
- `Actionable Guidance`
- `Evidence`
- `Open Questions`

## Writing Style

- Be concrete and practical.
- Prefer small examples over abstract claims.
- Explain why the lesson matters before giving advice.
- Include file paths and commands when they help reproduce or avoid the issue.
- State uncertainty directly when the lesson is based on incomplete evidence.

## Do Not Record

- Secrets, tokens, private data, customer data, or proprietary datasets.
- Model checkpoints, adapters, or full logs.
- Unverified claims phrased as facts.
- Multiple unrelated lessons in one note.
