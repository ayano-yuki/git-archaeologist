param(
  [string]$Config = "configs/collect/react_react.yaml",
  [string]$Repo = "",
  [string]$OutputDir = "",
  [int]$MaxPages = 0,
  [int]$PerPage = 0,
  [string]$Since = ""
)

$arguments = @("-m", "llm_tuning_lab.collect.github", "--config", $Config)

if ($Repo -ne "") {
  $arguments += @("--repo", $Repo)
}

if ($OutputDir -ne "") {
  $arguments += @("--output-dir", $OutputDir)
}

if ($MaxPages -gt 0) {
  $arguments += @("--max-pages", $MaxPages)
}

if ($PerPage -gt 0) {
  $arguments += @("--per-page", $PerPage)
}

if ($Since -ne "") {
  $arguments += @("--since", $Since)
}

uv run --system-certs python @arguments
