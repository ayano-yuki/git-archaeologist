# PR merge 後 cleanup 前ゲート

merge 済み PR の remote branch、local branch、git worktree を削除する前に使う確認ゲート。

## 発火条件

次の操作前に停止する。

- `git worktree remove`
- `git branch -d` / `git branch -D`
- `git push origin --delete <branch>`
- merge 後 cleanup を呼ぶ一括スクリプト

## 提示する情報

Cleanup Codex は次を人間に提示する。

- 対象 PR 番号、title、URL
- PR state が `MERGED` であること
- base branch と head branch
- 削除対象 remote branch
- 削除対象 local branch
- 削除対象 worktree path
- `git status --short --branch` の結果
- 未push commit がないこと
- 削除しない branch / worktree と理由
- 実行予定コマンド
- 復旧または代替案

## 人間レビュー観点

- 削除対象が PR head branch に限定されている。
- `main`、`phase/*`、通常運用中の `project/<function-area>` を削除しない。
- worktree が clean である。
- PR が merge 済みであり、未merge作業を消さない。
- remote branch 削除が必要な権限・所有関係にある。

## 再開条件

人間が cleanup を承認した後にだけ進める。PR が未merge、worktree が dirty、branch 名が PR head と一致しない、または削除対象が保護対象の場合は cleanup を実行せず停止する。
