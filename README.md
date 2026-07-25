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

実運用では `git_archaeologist.chat_flow.run_chat_flow` に Target Resolver、Evidence Retriever、Answer Generator、Citation Verifier の各backendを渡して利用します。Evidence Pack が空の場合や最新PR取得に失敗した場合は、根拠なしに断言せず安全な結果を返します。

## Phase2 動作確認

Phase2 の安定化機能は、外部サービスを呼ばない smoke で確認できます。増分同期、索引transaction、version付きcache、質問trace、障害fallback、失敗分類、RAG ablation、SFT判断を一周します。

```powershell
uv --system-certs run python -m git_archaeologist.phase2_smoke
```

`status` が `phase2_smoke_passed` であれば、MVPチャットとPhase2安定化部品が同じローカル環境で動作しています。

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

