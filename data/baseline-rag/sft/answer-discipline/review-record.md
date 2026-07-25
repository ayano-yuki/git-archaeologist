# SFT Answer Discipline Review

Dataset: `sft-records.jsonl`

Review status: curated

These records are synthetic answer-discipline examples. They are not raw GitHub artifacts and do not encode repository-specific facts that should be memorized. Each ideal answer is fully supported by its Evidence Pack and has no unsupported claims.

Checks:

- Evidence Pack reading is the training target.
- Closed-book repository facts are not taught.
- Citations refer to source IDs present in the same record.
- Splits do not share a decision unit.
