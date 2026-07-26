---
name: git-archaeologist-cleanup
description: "Git Archaeologist の merge 後 cleanup 役として、merge済みPRの remote branch、local branch、git worktree、追跡状態を安全に片付ける。使う場面: PR merge後の後始末、不要worktree削除、merged feature/project branch削除、local/remote branch整理。merge前や未push差分がある場合は停止する。"
---

# Git Archaeologist Cleanup

## 責務

Cleanup は merge 済みまたは明示的に close 済みの PR だけを扱う。未merge PR、未コミット差分、未push commit がある branch / worktree は削除しない。

## 最初に読む

- 対象 PR metadata: state、mergedAt、baseRefName、headRefName、headRepositoryOwner
- `.codex/rules/git-archaeologist-development.md`
- `.codex/rules/workflow.md`
- `.codex/rules/branches.md`
- `.codex/rules/cleanup.md`
- `.codex/rules/gates.md`
- `.codex/hooks/dangerous-operation-gate.md`
- `.codex/hooks/post-merge-cleanup-gate.md`

## merge 後 cleanup 手順

1. `gh pr view <pr>` で `state=MERGED` を確認する。
2. `git fetch --prune origin` で remote 状態を更新する。
3. 対象 head branch の worktree を `git worktree list` で探す。
4. worktree があれば、その worktree で `git status --short --branch` を確認する。
5. 未コミット差分、未push commit、未追跡の必要ファイルがあれば停止する。
6. clean なら `git worktree remove <path>` する。
7. local branch が merge 済みなら `git branch -d <branch>` で削除する。
8. remote branch が残っていれば `git push origin --delete <branch>` で削除する。
9. `git fetch --prune origin` 後、`git branch -a` と `git worktree list` で消えたことを確認する。

## remote branch 削除ルール

- 削除対象は PR の head branch のみ。
- fork PR や権限外 branch は削除を試みず、手順だけ報告する。
- `project/<function-area>` branch は、Manager が明示的に統合完了と判断した場合だけ削除する。通常は残す。
- `main`、`phase/*`、他人の作業 branch は削除しない。

## 停止条件

- PR が `MERGED` でない。
- 対象 branch に未push commit がある。
- worktree が dirty。
- branch 名が PR head と一致しない。
- 削除対象が `main`、`phase/*`、または無関係な branch。

## 報告

削除した remote branch、local branch、worktree path、残したものと理由を最後に報告する。
