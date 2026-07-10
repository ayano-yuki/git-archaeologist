# One Command SFT Runbook

## Summary

SFT を1コマンド化するときは、1つの巨大な処理に見せるのではなく、依存同期、データ収集、データ変換、検証、学習起動を順番に分けて設計する。利用者には `bash scripts/run_sft_linux.sh --preset react-react-qwen3-14b` だけを見せつつ、内部では失敗箇所が分かる粒度に保つ。

## Context

Git Archaeologist の SFT を、Linux の H100 環境で実行できるようにする作業。モデルは `Qwen/Qwen3-14B`、対象データは `react/react` の GitHub evidence。

## What Happened

`scripts/run_sft_linux.sh` を薄い入口として追加し、実行内容は `llm_tuning_lab.run.sft_pipeline` に寄せた。`--dry-run` では SFT を起動せず、依存同期から学習起動までのコマンド列を表示するようにした。

## Beginner Explanation

SFT は supervised fine-tuning の略で、入力と期待出力のペアを使ってモデルの答え方を調整する作業。失敗しやすい理由は、GPU だけでなく、データ形式、ファイルパス、依存関係、モデルダウンロード先、認証、出力先など多くの部品が関わるため。

1コマンド化は便利だが、内部の段階が見えないと失敗時に原因を探しにくくなる。そのため、外側は1コマンド、内側は段階的なコマンド列にする。

## Why It Matters

H100 の実行時間は高価で、エラーが起きてからデータ形式ミスに気づくのはもったいない。`--dry-run` と事前検証を用意しておくと、GPU を使う前に潰せる問題を先に潰せる。

## Actionable Guidance

- 実機に入る前に `--dry-run` でコマンド列を見る。
- SFT 本体の前に JSONL validate を必ず通す。
- bash スクリプトは薄くし、分岐や設定解釈は Python 側に寄せる。
- 失敗した段階が分かるように、収集、変換、検証、学習を別コマンドとして残す。

## Evidence

- 関連ファイル: `scripts/run_sft_linux.sh`
- 関連ファイル: `src/llm_tuning_lab/run/sft_pipeline.py`
- 関連コマンド: `uv run --system-certs --group dev python -m llm_tuning_lab.run.sft_pipeline --dry-run --skip-collect --preset react-react-qwen3-14b --include-sync-command`
- 確認結果: dry-run で `uv sync`、prepare、validate、train の順にコマンドが表示された。

## Open Questions

実機の Ubuntu 環境で、CUDA、bitsandbytes、Hugging Face のモデル取得、ディスク容量がすべて想定どおり動くかは未検証。
