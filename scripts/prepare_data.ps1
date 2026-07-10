param(
  [Parameter(Mandatory = $true)]
  [string]$InputPath,

  [Parameter(Mandatory = $true)]
  [string]$OutputPath
)

uv run --system-certs python -m llm_tuning_lab.data.prepare --input $InputPath --output $OutputPath
