# Roadmap Data Should Come From Reviewed Gold Cases

## Summary

Phase 2 RAFT-style data and Phase 3 DPO data should be materialized from reviewed Git Archaeologist gold cases, not directly from raw GitHub records. The same approved answer can teach evidence use in SFT/RAFT and become the `chosen` side of a DPO pair.

## Context

After confirming that fine-tuning can run, the repository needed a path through `.docs/fine-tuning-types.md` Phase 3: SFT + QLoRA, RAG-oriented SFT / RAFT style, and DPO.

## What Happened

The repository already had SFT materialization from `EvidenceBundle` plus reviewed gold cases. Phase 2 and Phase 3 were added as separate materializers that reuse the same validation gate, add distractor evidence for RAFT-style prompts, and produce `prompt/chosen/rejected` records for DPO.

## Beginner Explanation

Raw GitHub records are facts and context. A gold case is a reviewed training example that says which facts matter, which evidence IDs support them, what inference is reasonable, and what uncertainty remains. RAFT-style training uses retrieved evidence with distractors so the model practices choosing relevant evidence. DPO compares a better answer with a worse answer for the same prompt, so the model learns preference, not just format.

## Why It Matters

If Phase 2 or DPO data is generated directly from raw history, the model can learn to memorize repository content or copy weak signals. Starting from approved gold cases keeps the training target focused on reasoning style: citations, fact/inference separation, caution, and ignoring irrelevant evidence.

## Actionable Guidance

- Build or update `data/interim/bundles/*.jsonl` from raw GitHub records.
- Review `data/interim/gold_cases/*.jsonl` and approve only cases with valid citations and review metadata.
- Use `scripts/materialize_roadmap_data.ps1 -Mode raft` for Phase 2 messages JSONL.
- Use `scripts/materialize_roadmap_data.ps1 -Mode dpo` for Phase 3 preference JSONL.
- Validate DPO files with `scripts/validate_data.ps1 -Format dpo` before training.

## Evidence

- Related files: `src/llm_tuning_lab/data/roadmap.py`
- Related files: `src/llm_tuning_lab/train/dpo.py`
- Related commands: `.\scripts\materialize_roadmap_data.ps1 -Mode dpo -TrainOutput data\processed\dpo_train.jsonl -ValidationOutput data\processed\dpo_validation.jsonl`

## Open Questions

The default `rejected` answer is intentionally simple and synthetic. Later experiments should compare synthetic rejected answers with human-written rejected answers and judge whether DPO improves caution without making answers too timid.
