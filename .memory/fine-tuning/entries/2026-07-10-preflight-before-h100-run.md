# Preflight Before H100 Run

## Summary

H100 で SFT を回す前に、GPU を使わずに確認できる問題は先に潰す。JSONL 形式、空データ、設定ファイル、パス、dry-run、ユニットテストはローカルで確認できる。

## Context

Linux の H100 環境で `Qwen/Qwen3-14B` の LoRA SFT を回す準備。実機エラー対応は現地で行うが、それ以外の失敗は事前に減らす方針。

## What Happened

SFT 本体を起動せずに、`pytest`、dry-run、raw evidence から SFT JSONL への変換、生成 JSONL の検証を実行した。変換では `data/processed/train.jsonl` と `validation.jsonl` が生成され、validator を通過した。

## Beginner Explanation

GPU を使う学習は、始まってから失敗すると時間とコストを失いやすい。しかし、すべてのエラーが GPU に関係するわけではない。JSONL の形式ミス、ファイルがない、設定値が間違っている、出力先に書けない、といった問題は CPU だけでも確認できる。

preflight は「飛行前点検」のようなもの。学習を始める前に、必要な部品が揃っているかを確認する。

## Why It Matters

H100 で最初に見るべきエラーを、CUDA や依存ライブラリのような実機依存の問題に絞り込める。データ形式や設定のミスを先に消しておくと、現地対応が短くなる。

## Actionable Guidance

- `uv run --system-certs --group dev python -m pytest` を通す。
- `--dry-run` で実行予定コマンドを確認する。
- `data.prepare` を実行し、train と validation が空でないことを確認する。
- `data.validate` で生成 JSONL を検証する。
- `HF_HOME` を大容量ディスクに向ける。
- `outputs/` と `models/` は Git に入れない。

## Evidence

- 関連ファイル: `tests/test_github_sft_prepare.py`
- 関連ファイル: `tests/test_sft_pipeline.py`
- 関連ファイル: `.docs/linux-sft-runbook.md`
- 関連コマンド: `uv run --system-certs --group dev python -m pytest`
- 確認結果: 19 tests passed.
- 関連コマンド: `uv run --system-certs --group dev python -m llm_tuning_lab.data.validate data/processed/train.jsonl`
- 確認結果: `OK: data\processed\train.jsonl`
- 関連コマンド: `uv run --system-certs --group dev python -m llm_tuning_lab.data.validate data/processed/validation.jsonl`
- 確認結果: `OK: data\processed\validation.jsonl`

## Open Questions

実機でのみ確認できる CUDA、driver、bitsandbytes、Hugging Face download、ディスク速度、長時間学習の安定性は未検証。
