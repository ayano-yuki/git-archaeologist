param(
  [string]$ModelConfig = "configs/model/base.yaml",
  [string]$DataConfig = "configs/data/dpo.yaml",
  [string]$TrainConfig = "configs/train/dpo.yaml",
  [string]$LoraConfig = "configs/train/lora.yaml",
  [string]$TrainFile = "",
  [string]$ValidationFile = "",
  [string]$OutputDir = "",
  [switch]$PreflightOnly
)

$arguments = @(
  "-m", "llm_tuning_lab.train.dpo",
  "--model-config", $ModelConfig,
  "--data-config", $DataConfig,
  "--train-config", $TrainConfig,
  "--lora-config", $LoraConfig
)

if ($TrainFile -ne "") {
  $arguments += @("--train-file", $TrainFile)
}

if ($ValidationFile -ne "") {
  $arguments += @("--validation-file", $ValidationFile)
}

if ($OutputDir -ne "") {
  $arguments += @("--output-dir", $OutputDir)
}

if ($PreflightOnly) {
  $arguments += "--preflight-only"
}

uv run --system-certs python @arguments
