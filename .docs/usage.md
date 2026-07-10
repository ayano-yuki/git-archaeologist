# Repository Usage

## 目的

このリポジトリは Git Archaeologist 用の LLM ファインチューニング実験基盤です。

中心方針は、**知識は RAG、推論様式は Fine-tuning** です。GitHub の履歴そのものをモデルに覚えさせるのではなく、設計判断、原因分析、根拠引用、障害分析、レビュー思考を学習対象にします。

## ディレクトリ

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
.memory/   ファインチューニング知見
.codex/    Codex向けルールとSkill
```

## セットアップ

```powershell
uv sync --system-certs --extra train --group dev
uv run --system-certs pytest
```

この環境ではシステム証明書が必要になることがあるため、`uv` コマンドには `--system-certs` を付けます。

## よく使うコマンド

```powershell
.\scripts\collect_react_github.ps1 -MaxPages 1 -PerPage 10
.\scripts\validate_data.ps1 -Path data\samples\react_react_poc.jsonl
.\scripts\train_sft.ps1 -DataConfig configs/data/poc.yaml
.\scripts\eval_model.ps1
```

## Git管理しないもの

- 実データ
- 加工済み大規模データ
- checkpoint
- adapter
- merge済みモデル
- 評価結果の大量出力
- `.venv/` や cache

Gitに入れるのは、設定、コード、小さく安全なサンプル、Memory、Docsです。
