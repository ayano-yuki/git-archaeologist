param(
  [Parameter(Mandatory = $true)]
  [string]$InputPath,

  [string]$TrainOutputPath = "data/processed/train.jsonl",
  [string]$ValidationOutputPath = "data/processed/validation.jsonl",
  [double]$ValidationRatio = 0.2
)

uv run --system-certs python -m llm_tuning_lab.data.prepare `
  --input $InputPath `
  --train-output $TrainOutputPath `
  --validation-output $ValidationOutputPath `
  --validation-ratio $ValidationRatio
