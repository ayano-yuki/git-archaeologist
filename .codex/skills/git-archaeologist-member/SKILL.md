---
name: git-archaeologist-member
description: "Git Archaeologist の Member 役として、割り当てられた単一 Issue を専用 worktree で実装、テスト、コミット、push、規約どおりの PR 作成まで行う。使う場面: Issue番号を指定された実装、テスト、コミット、PR作成。Issue分解や複数Issue割り当てには使わない。"
---

# Git Archaeologist Member

## 責務

Member は1つの実施 Issue だけを扱う。同じ worktree で別 Issue の作業を混ぜない。

Manager から割り当てられていない複数 Issue を自分で束ねない。複数 Issue を受けた場合は Manager に戻し、並列化または逐次化の判断を受ける。

## 最初に読む

- 割り当て Issue 本文
- `.codex/rules/git-archaeologist-development.md`
- `.codex/rules/workflow.md`
- `.codex/rules/branches.md`
- `.codex/rules/pull-requests.md`
- `.codex/rules/data-and-layout.md`
- `.codex/rules/gates.md`
- `.codex/hooks/pr-create-gate.md`
- `.codex/hooks/dangerous-operation-gate.md`
- 必要に応じて `docs/plan.md` / `docs/Todo.md`

## ブランチと worktree

1. Issue の機能領域を確認する。
2. 対応 base branch は `project/<function-area>` に固定する。
3. project branch がない、古い、不明な場合は停止し、Manager に修復を戻す。
4. `feature/<issue-number>-<short-title>` を `project/<function-area>` から作る。
5. `git worktree` で Issue 専用作業ディレクトリを作る。

## 実装

1. Issue の受け入れ条件だけを満たす。
2. 依存追加、CI/CD、認証、保存場所変更、大量削除、破壊的操作は事前に停止する。
3. テスト方針に沿って検証する。
4. コミットメッセージは `接頭語: 日本語の内容` にする。

## PR 作成前 fail-fast

PR 作成前に必ず base/head を検査する。

- OK: `feature/<issue-number>-<short-title> -> project/<function-area>`
- NG: `feature -> main`
- NG: `feature -> feature`
- NG: `project -> feature`

NG の場合は PR を作らず、正しい project branch へ rebase/cherry-pick する方針を提示して停止する。

## PR 作成

1. `.codex/hooks/pr-create-gate.md` の項目で人間確認を受ける。
2. 承認後に push し、PR を作成する。
3. PR URL を報告する。push だけで終了しない。
4. PR 作成後、worktree は clean かつ upstream 追跡済みであることを確認する。

## merge 後

PR merge 後の branch / worktree 削除は `git-archaeologist-cleanup` に渡す。Member は merge 前に勝手に remote branch や worktree を消さない。
