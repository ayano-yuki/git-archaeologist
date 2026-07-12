param(
  [string]$Path = "data/samples/sft_sample.jsonl",
  [ValidateSet("messages", "dpo", "preference")]
  [string]$Format = "messages"
)

uv run --system-certs python -m llm_tuning_lab.data.validate $Path --format $Format
