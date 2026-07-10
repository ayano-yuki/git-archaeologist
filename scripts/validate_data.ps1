param(
  [string]$Path = "data/samples/sft_sample.jsonl"
)

uv run --system-certs python -m llm_tuning_lab.data.validate $Path
