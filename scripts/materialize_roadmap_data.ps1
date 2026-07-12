param(
  [ValidateSet("raft", "dpo")]
  [string]$Mode = "raft",
  [string]$Bundles = "data/interim/bundles/react-react.jsonl",
  [string]$GoldCases = "data/interim/gold_cases/react-react.jsonl",
  [string]$TrainOutput = "",
  [string]$ValidationOutput = "",
  [string]$Output = "",
  [double]$ValidationRatio = 0.1,
  [int]$DistractorsPerRecord = 2,
  [int]$MaxSeqLength = 2048,
  [switch]$AllowUnapproved
)

$arguments = @(
  "-m", "llm_tuning_lab.data.roadmap",
  $Mode,
  "--bundles", $Bundles,
  "--gold-cases", $GoldCases,
  "--distractors-per-record", "$DistractorsPerRecord"
)

if ($TrainOutput -ne "" -and $ValidationOutput -ne "") {
  $arguments += @(
    "--train-output", $TrainOutput,
    "--validation-output", $ValidationOutput,
    "--validation-ratio", "$ValidationRatio"
  )
}

if ($Output -ne "") {
  $arguments += @("--output", $Output)
}

if ($Mode -eq "raft") {
  $arguments += @("--max-seq-length", "$MaxSeqLength")
}

if ($AllowUnapproved) {
  $arguments += "--allow-unapproved"
}

uv run --system-certs python @arguments
