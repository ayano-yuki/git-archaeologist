#!/usr/bin/env sh
set -eu

show_help() {
  cat <<'EOF'
Run the Linux SFT pipeline.

Usage:
  bash scripts/run_sft_linux.sh --preset react-react-qwen3-14b

Options:
  --preset NAME_OR_PATH   Run preset name or YAML path. Default: react-react-qwen3-14b
  --skip-collect          Use existing data/raw GitHub JSONL files.
  --insecure-ssl          Disable TLS verification for GitHub collection.
  --dry-run               Print commands without running collection, prepare, validation, or SFT.
  -h, --help              Show this help.

Environment:
  GITHUB_TOKEN            Optional GitHub API token for higher rate limits.
  HF_TOKEN                Optional Hugging Face token for gated/private models.
  HF_HOME                 Optional cache directory for model downloads.
EOF
}

has_arg() {
  expected="$1"
  shift
  for arg in "$@"; do
    if [ "$arg" = "$expected" ]; then
      return 0
    fi
  done
  return 1
}

if has_arg "-h" "$@" || has_arg "--help" "$@"; then
  show_help
  exit 0
fi

if has_arg "--dry-run" "$@"; then
  uv run --system-certs --group dev python -m llm_tuning_lab.run.sft_pipeline \
    --include-sync-command "$@"
  exit $?
fi

uv sync --system-certs --extra train --group dev
uv run --system-certs python -m llm_tuning_lab.run.sft_pipeline "$@"
