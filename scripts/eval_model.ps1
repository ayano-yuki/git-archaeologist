param(
  [string]$Benchmark = "evals/benchmarks/smoke.jsonl",
  [string]$Predictions = "evals/results/smoke_predictions.jsonl",
  [string]$Output = "evals/results/smoke_metrics.json",
  [switch]$Strict,
  [switch]$FailOnInvalid,
  [double]$MinCoverage,
  [double]$MinFactRecall,
  [double]$MinAnswerSimilarity,
  [double]$MinTimelineEventRecall
)

$EvalArgs = @(
  "run",
  "--system-certs",
  "python",
  "-m",
  "llm_tuning_lab.eval.run_eval",
  "--benchmark",
  $Benchmark,
  "--predictions",
  $Predictions,
  "--output",
  $Output
)

if ($Strict) {
  $EvalArgs += "--strict"
}
if ($FailOnInvalid) {
  $EvalArgs += "--fail-on-invalid"
}
if ($PSBoundParameters.ContainsKey("MinCoverage")) {
  $EvalArgs += @("--min-coverage", $MinCoverage)
}
if ($PSBoundParameters.ContainsKey("MinFactRecall")) {
  $EvalArgs += @("--min-fact-recall", $MinFactRecall)
}
if ($PSBoundParameters.ContainsKey("MinAnswerSimilarity")) {
  $EvalArgs += @("--min-answer-similarity", $MinAnswerSimilarity)
}
if ($PSBoundParameters.ContainsKey("MinTimelineEventRecall")) {
  $EvalArgs += @("--min-timeline-event-recall", $MinTimelineEventRecall)
}

& uv @EvalArgs
exit $LASTEXITCODE
