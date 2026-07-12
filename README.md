# Git Archaeologist Tuning Lab

Git Archaeologist 用の LLM ファインチューニング実験を、データ準備、学習、評価、成果物管理に分けて扱うためのリポジトリです。

Git Archaeologist は、コードベースの現在形だけでなく、Commit、PR、Issue、Review、Revert、CI ログなどの履歴から「なぜこの実装になったのか」を説明するローカル LLM を目指します。

このリポジトリの基本方針は、知識は RAG、推論様式は Fine-tuning です。GitHub の履歴そのものをモデルに覚えさせるのではなく、設計判断、原因分析、根拠引用、障害分析、レビュー思考を学習対象にします。

## Layout

```text
configs/   実験、モデル、データ設定
data/      ローカルデータと小さなサンプル
src/       再利用する Python パッケージ
scripts/   よく使う実行コマンド
evals/     評価プロンプト、期待値、結果置き場
outputs/   学習ログや checkpoint
models/    adapter や merge 済みモデル
tests/     データ形式やユーティリティのテスト
.docs/     リポジトリの使い方と手順
.memory/   ファインチューニングの知見、失敗、注意点
.codex/    Codex向けルール、Skill、開発補助設定
```

## Quick Start

```powershell
uv sync --system-certs --extra train --group dev
uv run --system-certs python -m llm_tuning_lab.data.validate data/samples/sft_sample.jsonl
uv run --system-certs pytest
```

Linux の H100 環境で `react/react` の収集から SFT 起動までをまとめて確認する場合:

```bash
bash scripts/run_sft_linux.sh --preset react-react-qwen3-14b
```

SFT 本体を起動せずに実行予定コマンドだけ確認する場合:

```bash
bash scripts/run_sft_linux.sh --dry-run --preset react-react-qwen3-14b
```

PoC 用のサンプル設定で学習する場合は、データを差し替えてから同じ入口を使います。

```powershell
.\scripts\collect_react_github.ps1 -MaxPages 1 -PerPage 10
.\scripts\validate_data.ps1 -Path data/samples/react_react_poc.jsonl
.\scripts\train_sft.ps1 -DataConfig configs/data/poc.yaml
```

Phase 2 の RAG-oriented SFT / RAFT 型データ、Phase 3 の DPO preference data は、既存の evidence bundle と承認済み gold case から materialize します。下のコマンドは `data/interim/bundles/...` と `data/interim/gold_cases/...` をローカルで用意した後の例で、fresh checkout だけでは実行できません。

```powershell
.\scripts\materialize_roadmap_data.ps1 -Mode raft -TrainOutput data\processed\raft_train.jsonl -ValidationOutput data\processed\raft_validation.jsonl
.\scripts\materialize_roadmap_data.ps1 -Mode dpo -TrainOutput data\processed\dpo_train.jsonl -ValidationOutput data\processed\dpo_validation.jsonl
.\scripts\validate_data.ps1 -Path data\processed\dpo_train.jsonl -Format dpo
.\scripts\train_dpo.ps1 -DataConfig configs\data\dpo.yaml -PreflightOnly
```

既定のモデル設定は `Qwen/Qwen3-14B` です。H100 1枚環境でまず学習パイプラインを確認し、その後 `Qwen/Qwen2.5-Coder-32B-Instruct` などの本命候補に切り替える想定です。

## PoC Data

PoC では、`React` と `react` の使い分けを題材にした小さな JSONL データを使います。

このデータは、UI ライブラリ名としての `React` と、英語の動詞としての `react` を文脈で区別するための最小サンプルです。実際の用途では、`configs/data/poc.yaml` の `train_file` を差し替えるだけで、同じ学習入口を使えます。

```yaml
train_file: data/samples/react_react_poc.jsonl
validation_file:
format: messages
```

## Data Format

Supervised fine-tuning data is JSONL. Each line should use a `messages` array.

```json
{"messages":[{"role":"system","content":"You explain repository history using evidence first, then cautious inference."},{"role":"user","content":"Issue #42 and PR #57 show that sync auth calls were kept after an outage. Why might the code still be synchronous?"},{"role":"assistant","content":"Evidence: Issue #42 describes an outage caused by token refresh races, and PR #57 keeps the auth path synchronous while adding retry logging. Inference: the synchronous behavior was likely kept to preserve ordering around token refresh."}]}
```

## Fine-tuning Flow

PoC の小さな `messages` JSONL はそのまま `scripts/train_sft.ps1` で学習できます。本命の Git Archaeologist データでは、GitHub の raw record を直接 SFT にせず、調査ケース単位に変換します。

1. GitHub evidence を `data/raw/github/<repo>/` に収集する。
2. `llm_tuning_lab.data.bundles` で Issue / PR / Commit / Review / Diff / CI を `EvidenceBundle` にまとめる。
3. 人間作成または外部作成済みの `GoldCase` を `data/interim/gold_cases/` に置く。教師モデルによる回答生成は行わない。
4. `llm_tuning_lab.data.gold_cases validate` で引用、時系列、不確実性、レビューmetadata、bundle/evidence hashを検証する。
5. `review_status: approved` の case だけを train / validation / test と benchmark に materialize する。
6. benchmark に対する base / RAG / SFT / SFT+RAG の予測 JSONL を `llm_tuning_lab.eval.run_eval` で採点する。missing predictionは0点としてcoverageに反映し、facts / timeline / answer / inference の近似一致も見る。
7. `outputs/` に学習成果物と `training_manifest.json` を保存し、Git にはコミットしない。

## Memory

ファインチューニングに関する知見は `.memory/fine-tuning/` に残します。成功例だけでなく、注意点、失敗、うまくいかなかった仮説、評価で見つかった問題も記録します。

新しい知見を書くときは、初学者に説明するつもりで背景から書きます。何が起きたか、なぜ重要か、次にどうすればよいかを分けて残します。

詳しい使い方は `.docs/usage.md`、ファインチューニング手順は `.docs/fine-tuning.md` にまとめています。
Linux 実環境での1コマンド実行手順は `.docs/linux-sft-runbook.md` にまとめています。

## Notes

- Keep large data and model artifacts out of git.
- Use `uv sync --system-certs` and `uv run --system-certs` for the development environment.
- Use `configs/` to make experiments repeatable.
- Run validation before training.
- Keep factual repository knowledge in the retrieval layer.
- Use fine-tuning to improve reasoning over retrieved evidence.
