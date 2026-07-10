# Fine-tuning Memory Writing Guide

## Purpose

Write notes that help a future beginner understand the fine-tuning lesson without needing the original conversation.

## What Counts as a Lesson

- A failure and its cause.
- A warning about data, model settings, evaluation, or environment setup.
- A small successful pattern worth repeating.
- A distinction that prevents confusion, such as what belongs in RAG versus fine-tuning.
- An evaluation result that changes how future experiments should be run.

## Beginner-first Explanation

Assume the reader knows basic Python but is new to LLM fine-tuning.

Define terms the first time they matter:

- SFT: supervised fine-tuning, where examples teach the model desired input-output behavior.
- JSONL: one JSON object per line, commonly used for training data.
- LoRA: a lightweight adapter method that trains a small number of parameters.
- RAG: retrieval-augmented generation, where facts are retrieved at answer time instead of memorized.

## Fact Versus Interpretation

Use this split:

- Fact: commands run, files changed, validation errors, observed model behavior.
- Interpretation: likely cause, inferred tradeoff, recommended next step.

Do not hide uncertainty. Write "likely", "not yet verified", or "needs another run" when appropriate.

## Good Evidence

Good evidence includes:

- File paths.
- Commands.
- Short error excerpts.
- Config values.
- Dataset shape or small sanitized examples.
- Evaluation metrics.

Avoid long logs. Summarize them and point to the command that produced them.
