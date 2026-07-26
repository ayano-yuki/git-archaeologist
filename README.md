# Git Archaeologist

Git Archaeologist は、GitHub Repository に蓄積された Commit、Pull Request、Issue、Review、Revert、CI ログを横断的に分析し、「なぜこの実装が現在の形になったのか」を根拠付きで説明するローカル AI システムです。

詳細なプロダクト計画は `docs/plan.md`、実装タスクは `docs/Todo.md` を参照してください。

## 開発環境

Python 開発には `uv` を使います。

```powershell
uv lock
uv --system-certs run python -c "import git_archaeologist; print(git_archaeologist.__all__)"
```

環境によって `uv run` が証明書エラーになる場合があるため、このリポジトリでは `uv --system-certs run ...` を推奨します。

## MVPチャットデモ

外部サービスを呼ばない決定的なデモとして、入力解釈、対象解決、Evidence Pack取得、回答生成、引用検証までを一周できます。

```powershell
uv --system-certs run python -m git_archaeologist.demo_chat
```

実運用では `git_archaeologist.chat.chat_flow.run_chat_flow` に Target Resolver、Evidence Retriever、Answer Generator、Citation Verifier の各backendを渡して利用します。Evidence Pack が空の場合や最新PR取得に失敗した場合は、根拠なしに断言せず安全な結果を返します。

## ローカル Smoke 確認

外部サービスを呼ばない smoke で、安定化、障害分析、lineage 分析をまとめて確認できます。増分同期、索引transaction、version付きcache、質問trace、障害fallback、失敗分類、RAG ablation、SFT判断、incident graph、行・条件分岐分析を一周します。

```powershell
uv --system-certs run python -m git_archaeologist.ops.smoke
```

`status` が `local_smoke_passed` であれば、MVPチャットと主要な分析部品が同じローカル環境で動作しています。

## セットアップ確認

ローカル運用を始める前に、Repository設定、storage layout、`gh` 認証、runtime profile、本番データ学習 readiness、初回索引手順を一括で確認できます。setup の合否と、重い学習実行まで進められるかは別フィールドとして表示されます。

```powershell
uv --system-certs run python -m git_archaeologist.ops.setup --dry-run
```

外部サービスに触れずに設定とローカル状態だけを確認する場合は、GitHub access check を明示的にスキップします。

```powershell
uv --system-certs run python -m git_archaeologist.ops.setup --dry-run --skip-github-access
```

storage directory を作成する場合だけ `--execute` を使います。setup は外部収集や破壊的な削除を実行しません。

```powershell
uv --system-certs run python -m git_archaeologist.ops.setup --execute --skip-github-access
```

## 同期状態確認

同期状態は、外部収集を実行せずに status と manual sync plan を確認できます。

```powershell
uv --system-certs run python -m git_archaeologist.ops.sync --status
uv --system-certs run python -m git_archaeologist.ops.sync --plan
```

scheduler は設定内容をレポートするだけで、OS の常駐ジョブやGitHub状態は変更しません。

## FT / QLoRA 動作確認

Answer / Judge LLM の回答規律を SFT する場合は、先に構成全体の smoke を実行します。

```powershell
uv --system-certs run python -m git_archaeologist.evaluation.system_smoke
```

学習用依存関係も含めて確認する場合は、training extra を使います。

```powershell
uv sync --extra training
uv --system-certs run --extra training python -m git_archaeologist.evaluation.system_smoke --require-training-dependencies
uv --system-certs run --extra training python -m git_archaeologist.evaluation.train_sft --dry-run
```

サーバーで GPU とモデルロードまで確認する最小実行は次のコマンドです。

```powershell
uv --system-certs run --extra training python -m git_archaeologist.evaluation.train_sft --execute --max-steps 1
```

本番学習は `--max-steps` を外して実行します。対象モデルは runtime profile で選定した `Qwen/Qwen2.5-Coder-7B-Instruct`、方式は QLoRA です。adapter は `data/Qwen--Qwen2.5-Coder-7B-Instruct/models/answer-discipline-qlora/` へ出力します。

学習後は post-FT 評価を実行し、adapter成果物、学習summary、closed-book漏洩契約、baseline / prompt / SFT 比較を確認します。

```powershell
uv --system-certs run python -m git_archaeologist.evaluation.post_sft_evaluation
```

レポートは `data/Qwen--Qwen2.5-Coder-7B-Instruct/eval/post-sft/answer-discipline-post-sft-report.json` に保存されます。

## ディレクトリ構成

```text
src/
  git_archaeologist/

data/
  <model-name>/

docs/
  plan.md
  Todo.md

.codex/
  orchestration/
  rules/
  hooks/
  skills/

.agents/
```

- コードは `src/` 配下に置きます。
- Python パッケージコードは `src/git_archaeologist/` 配下に置きます。
- 学習・評価・実験用データは `data/<model-name>/` 配下に置きます。
- `data/` の詳細な配置ルールは `data/README.md` を参照してください。
- Codex Manager / Member の運用資材は `.codex/` と `.agents/` に置きます。

## Codex 並列開発

このリポジトリでは、Codex を Manager / Member として運用し、Issue 単位で並列開発します。

- `AGENTS.md`: Codex が最初に読むガイド。
- `.agents/manager.md`: Manager Codex の責務。
- `.agents/member.md`: Member Codex の責務。
- `.codex/rules/git-archaeologist-development.md`: ブランチ、コミット、PR、停止条件のルール。
- `.codex/orchestration/templates/`: Issue / PR テンプレート。
