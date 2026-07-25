# Git Archaeologist Agent ガイド

このリポジトリでは、Codex を Manager / Member として運用し、Issue 単位の並列開発を行う。

## 最初に読むもの

1. `docs/plan.md`: プロダクト全体像とフェーズ構成を把握する。
2. `docs/Todo.md`: 実装タスク、完了条件、フェーズゲートを確認する。
3. `.codex/skills/git-archaeologist-dev/SKILL.md`: Issue 分解、Member 作業、PR 作成、レビュー対応の運用を確認する。
4. `.codex/rules/git-archaeologist-development.md`: ブランチ、コミット、PR、停止条件のルールを確認する。

## 役割

### Manager Codex

- 親 Issue から子 Issue 案を一括作成する。
- 人間の微調整後、`gh` で子 Issue を一括作成するためのコマンド案を出す。
- 子 Issue を Member Codex に割り当てる。
- Member の PR を人間レビュー前に一次レビューする。
- レビュー指摘を読み、元 Member または別 Member に再割り当てする。

### Member Codex

- 割り当てられた Issue を 1 つ担当する。
- `git worktree` で Issue ごとの作業ディレクトリを分ける。
- 実装、テスト、コミット、PR 作成まで行う。
- PR 作成前に設計ズレ、受け入れ条件、テスト結果を確認する。

## 人間確認ゲート

次の操作前には、人間が設計ズレを確認できる形で止まる。

- 子 Issue を一括作成する前。
- PR を作成する前。
- 依存追加、設定変更、CI/CD 変更、破壊的 git 操作、広範囲削除・移動を行う前。

## ブランチ規約

ブランチは次の階層で扱う。

```text
main
phase/1-mvp
project/<function-area>
feature/<issue-number>-<short-title>
```

`project/<function-area>` は次のいずれかを使う。

- `project/collector`
- `project/normalizer`
- `project/search`
- `project/rag`
- `project/chat`
- `project/evaluation`

## 開発配置

- Python 開発は `uv` を使う。
- 証明書エラーで `uv run` が失敗する環境では `uv --system-certs run ...` を使う。
- コードは `src/`、パッケージコードは `src/git_archaeologist/` に置く。
- 学習・評価・実験用データは `data/` に置く。
- `data/` はモデルごとにフォルダーを分け、詳細は `data/README.md` に従う。

## コミットと PR

- コミットメッセージは `接頭語: 日本語の内容` とする。
- PR タイトルは `[機能] PR内容（#issue番号）` とする。
- PR 本文には関連 Issue を `- [issue] #123` の形式で書く。
- PR 本文には受け入れ条件、テスト結果、Manager 一次レビューの観点を含める。
