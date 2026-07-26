# Git Archaeologist 開発ルール入口

このファイルは全体ルールの入口だけを持つ。具体ルールは責務別ファイルに分け、作業ロールに必要なものだけ読む。

## 最初に読む

- 共通: `.codex/rules/workflow.md`
- Issue 作成、phase 整理、Member 割り当て: `.codex/rules/issues.md`
- branch、worktree、PR topology: `.codex/rules/branches.md`
- commit、PR 作成、一次レビュー: `.codex/rules/pull-requests.md`
- merge 後 cleanup: `.codex/rules/cleanup.md`
- 開発配置、data 管理: `.codex/rules/data-and-layout.md`
- 停止条件、人間確認: `.codex/rules/gates.md`

## Role 別読み込み

- `git-archaeologist-manager`: `workflow.md`, `issues.md`, `branches.md`, `gates.md`
- `git-archaeologist-member`: `workflow.md`, `branches.md`, `pull-requests.md`, `data-and-layout.md`, `gates.md`
- `git-archaeologist-reviewer`: `workflow.md`, `branches.md`, `pull-requests.md`, `gates.md`
- `git-archaeologist-cleanup`: `workflow.md`, `branches.md`, `cleanup.md`, `gates.md`

## 全ロール共通の絶対ルール

- 作業開始前に Manager が依頼内容、Issue、phase、依存関係、機能領域、並列化可否を整理する。
- Manager は実装しない。実装は必ず Member として開始する。
- Member は 1 Issue だけを扱い、Issue ごとに worktree を分ける。
- PR は隣接階層だけに作る。
- `feature -> main`、`feature -> feature`、`project -> feature` の PR は作らない。
- PR merge 後の branch / worktree 削除は Cleanup として行う。
