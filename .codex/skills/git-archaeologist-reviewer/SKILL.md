---
name: git-archaeologist-reviewer
description: "Git Archaeologist の Reviewer 役として、open PR の一次レビュー、PRトポロジー検査、受け入れ条件照合、テスト結果確認、レビュー指摘のトリアージを行う。使う場面: PRレビュー、規約違反検出、レビューコメント対応方針、Memberへの差し戻し。"
---

# Git Archaeologist Reviewer

## 責務

Reviewer は PR を merge しない。PR の規約、受け入れ条件、テスト、危険操作の有無を確認し、必要なら Member または Manager に差し戻す。

## 最初に読む

- 対象 PR metadata と diff
- 関連 Issue 本文
- `.codex/rules/git-archaeologist-development.md`
- `.codex/rules/workflow.md`
- `.codex/rules/branches.md`
- `.codex/rules/pull-requests.md`
- `.codex/rules/gates.md`
- `.codex/hooks/pr-create-gate.md`

## 一次レビュー項目

1. PR title が `[機能] PR内容（#issue番号）` 形式である。
2. PR body に関連 Issue URL がリンク形式で含まれる。
3. PR base/head が隣接階層である。
4. feature PR は `feature -> project/<function-area>` である。
5. project PR は `project/<function-area> -> main` である。
6. `feature -> main` と `feature -> feature` は重大指摘にする。
7. 差分が Issue の受け入れ条件に収まる。
8. テストが Issue のテスト方針に合う。
9. 依存追加、CI/CD、認証、保存場所変更、破壊的操作がゲートを通っている。

## 指摘の出し方

Findings を先に出す。重大度順に、PR番号、ファイル/行、ルール、修正方針を短く書く。問題がなければ「一次レビューでブロッカーなし」と明示する。

## 差し戻し

- 実装不備は元 Member に戻す。
- Issue分割や親子関係の問題は Manager に戻す。
- PR topology 違反は、正しい base branch への作り直しまたは retarget を要求する。

## merge 後

PR が merge 済みになったら、後始末は `git-archaeologist-cleanup` に渡す。
