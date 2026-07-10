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

PoC 用のサンプル設定で学習する場合は、データを差し替えてから同じ入口を使います。

```powershell
.\scripts\validate_data.ps1 -Path data/samples/react_react_poc.jsonl
.\scripts\train_sft.ps1 -DataConfig configs/data/poc.yaml
```

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

1. JSONL データを `messages` 形式で用意する。
2. `scripts/validate_data.ps1` で形式を検証する。
3. `configs/data/*.yaml` の `train_file` を差し替えるか、`scripts/train_sft.ps1 -TrainFile ...` を指定する。
4. `configs/model/base.yaml`, `configs/train/sft.yaml`, `configs/train/lora.yaml` を調整する。
5. `outputs/` に学習成果物を保存し、Git にはコミットしない。

## Memory

ファインチューニングに関する知見は `.memory/fine-tuning/` に残します。成功例だけでなく、注意点、失敗、うまくいかなかった仮説、評価で見つかった問題も記録します。

新しい知見を書くときは、初学者に説明するつもりで背景から書きます。何が起きたか、なぜ重要か、次にどうすればよいかを分けて残します。

詳しい使い方は `.docs/usage.md`、ファインチューニング手順は `.docs/fine-tuning.md` にまとめています。

## Notes

- Keep large data and model artifacts out of git.
- Use `uv sync --system-certs` and `uv run --system-certs` for the development environment.
- Use `configs/` to make experiments repeatable.
- Run validation before training.
- Keep factual repository knowledge in the retrieval layer.
- Use fine-tuning to improve reasoning over retrieved evidence.
