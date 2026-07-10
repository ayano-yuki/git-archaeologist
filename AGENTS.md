# Repository Rules

This repository is for LLM fine-tuning experiments for Git Archaeologist, a local LLM project that reconstructs design intent and causal history from repository evidence. Keep it reproducible, data-safe, and easy to compare across runs.

## Structure

- Put reusable Python code under `src/llm_tuning_lab/`.
- Put experiment settings under `configs/`.
- Put small committed examples under `data/samples/`.
- Do not commit real datasets, processed corpora, checkpoints, adapters, merged models, or evaluation result dumps.
- Put generated outputs under `outputs/`, `models/`, or `evals/results/`.

## Data Safety

- Treat `data/raw/`, `data/interim/`, and `data/processed/` as local-only unless explicitly approved.
- Commit only tiny, sanitized examples that are safe to share.
- Prefer JSONL for supervised fine-tuning data.
- Validate every training file before running a training job.

## Git Archaeologist Tuning Policy

- Do not fine-tune the model to memorize GitHub history, repository contents, private issues, or private reviews.
- Use RAG for factual repository knowledge such as commits, issues, PRs, reviews, CI logs, release notes, and blame.
- Use fine-tuning for reasoning style: design decision reconstruction, causal analysis, evidence citation, revert analysis, risk analysis, and review thinking.
- Training samples should teach how to use evidence, distinguish facts from inference, and explain uncertainty.
- Evaluation should compare at least RAG-only and RAG-plus-fine-tuning behavior when possible.

## Experiments

- Add or update a config file for each repeatable experiment.
- Keep model, data, training, and evaluation choices in config files rather than hard-coded scripts.
- Use deterministic seeds where possible.
- Save logs and artifacts outside git-managed paths.
- Use `uv sync --system-certs` and `uv run --system-certs` for Python dependency management and command execution.

## Fine-tuning Memory

- Record fine-tuning lessons under `.memory/fine-tuning/` when new knowledge, warnings, failures, or useful examples emerge.
- Write memory notes for beginners: explain context, terms, what happened, why it matters, and what to do next.
- Keep one memory note focused on one lesson.
- Do not include private data, secrets, full datasets, checkpoints, or long logs in memory notes.

## Code Changes

- Keep hand-authored files under 500 lines. Split responsibilities into smaller modules before a file grows beyond that limit. Generated lockfiles are exempt.
- Keep scripts thin; shared behavior belongs in `src/llm_tuning_lab/`.
- Add focused tests for data formatting, prompt templating, and config assumptions.
- Avoid broad refactors unless they directly support the tuning workflow.
