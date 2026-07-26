# Gate / Stop ルール

次の操作前には停止して、人間に確認内容を提示する。

- 子 Issue の一括作成。
- PR 作成。
- PR base/head が規約外である、または対応 project branch が存在しない。
- 新しい依存関係の追加。
- 設定ファイル、CI/CD、GitHub Actions、認証、秘密情報、保存場所の変更。
- 破壊的 git 操作。
- 大量削除、移動、リネーム。
- merge 済み確認が取れていない branch / worktree cleanup。
- PR merge 後に remote branch、local branch、worktree を削除する操作。
- `docs/plan.md` または `docs/Todo.md` のロードマップ変更。

## Hook

- Issue 作成前: `.codex/hooks/issue-create-gate.md`
- PR 作成前: `.codex/hooks/pr-create-gate.md`
- merge 後 cleanup 前: `.codex/hooks/post-merge-cleanup-gate.md`
- 危険操作前: `.codex/hooks/dangerous-operation-gate.md`
