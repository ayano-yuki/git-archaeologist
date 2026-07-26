# Cleanup ルール

## 対象

- PR merge 後の remote branch、local branch、worktree 削除は `git-archaeologist-cleanup` の責務とする。
- 削除対象は PR の head branch に限定する。
- `main`、`phase/*`、通常運用中の `project/<function-area>` は削除しない。

## 実行前確認

- `gh pr view <pr>` で `state=MERGED` を確認する。
- 対象 worktree が clean であることを確認する。
- 対象 branch に未 push commit がないことを確認する。
- branch 名が PR head branch と一致することを確認する。

## 実行

- remote branch は `git push origin --delete <branch>` を使う。
- local branch は `git branch -d <branch>` を使う。
- worktree は `git worktree remove <path>` を使う。
- 最後に `git fetch --prune origin` と `git worktree list` で確認する。

## 停止条件

- dirty worktree
- 未 merge PR
- 未 push commit
- branch 名不一致
- fork / 権限外 branch
- 削除対象が `main`、`phase/*`、通常運用中の `project/<function-area>`
