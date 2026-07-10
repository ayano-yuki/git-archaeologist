param(
  [string]$ModelConfig = "configs/model/base.yaml",
  [string]$DataConfig = "configs/data/sft.yaml",
  [string]$TrainConfig = "configs/train/sft.yaml",
  [string]$LoraConfig = "configs/train/lora.yaml",
  [string]$TrainFile = "",
  [string]$ValidationFile = "",
  [string]$OutputDir = ""
)

$arguments = @(
  "-m", "llm_tuning_lab.train.sft",
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

uv run --system-certs python @arguments
