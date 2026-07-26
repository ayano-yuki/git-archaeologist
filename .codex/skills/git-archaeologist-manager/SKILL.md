---
name: git-archaeologist-manager
description: "Git Archaeologist の Manager 役として、作業開始前に依頼内容、対象Issue、phase、受け入れ条件、依存関係、機能領域、並列化可否を整理し、親PBI/phase Issueから実施 Issue を分解し、sub-issue 作成案、Member 並列割り当て、PR漏れ確認を行う。使う場面: Issue 分解、phase Issue 作成、一括 Issue 作成、Member への作業割り当て、push済みbranchとPR対応確認。実装作業そのものには使わない。"
---

# Git Archaeologist Manager

## 責務

Manager は計画、Issue 整理、割り当て、PR漏れ確認だけを行う。コード実装、コミット、PR作成は `git-archaeologist-member` に渡す。

## 最初に読む

- `docs/plan.md`
- `docs/Todo.md`
- `.codex/rules/git-archaeologist-development.md`
- `.codex/rules/workflow.md`
- `.codex/rules/issues.md`
- `.codex/rules/branches.md`
- `.codex/rules/gates.md`
- `.codex/hooks/issue-create-gate.md`
- `.codex/orchestration/templates/child-issue.md`
- `.codex/orchestration/templates/issue-batch-plan.md`

## ワークフロー

1. 親PBI `ayano-yuki/ayano-yuki-pbi#58` と対象 phase Issue を確認する。
2. phase Issue がなければ `【git-archaeologist 】 phaseNN` を #58 の sub-issue として作る案を準備する。
3. `docs/Todo.md` の未完了項目を、Member が1 Issueで実装できる粒度へ分割する。
4. 各 Issue に `collector` / `normalizer` / `search` / `rag` / `chat` / `evaluation` の機能領域を必ず設定する。
5. 実施 Issue は対応する phase Issue の sub-issue にする。
6. Issue 作成前に `.codex/hooks/issue-create-gate.md` の内容で停止し、人間確認を受ける。
7. 承認後に Issue を作成し、`parent` / `subIssues` を確認する。
8. 各 Issue を `git-archaeologist-member` の作業単位として割り当てる。
9. 独立して進められる Issue は並列 Member 起動対象として明示する。

## 並列 Member 割り当て

Manager は作業開始前に、Issue ごとの独立性を判定する。

- 並列可: 受け入れ条件、主要ファイル、機能領域、依存関係が衝突しない。
- 逐次: 依存 Issue がある、同じファイルを広く触る、base branch 修復が必要。
- 不明: Issue を再分割するか、人間に確認する。

並列可と判断した場合は、Issue 番号、機能領域、base branch、worktree 名、開始順を Member ごとに渡す。

## PR トポロジー確認

Manager は Member に渡す前に、対応 project branch を確認する。

- `feature/<issue-number>-<short-title>` の PR base は必ず `project/<function-area>`。
- `project/<function-area>` の PR base は必ず `main`。
- `feature -> main`、`feature -> feature`、`project -> feature` は禁止。
- 対応 project branch がない場合は、作成方針を人間確認してから進める。

## PR 漏れ確認

最終報告前に `gh pr list` などで、push 済み feature branch に open PR があるか確認する。PR がなければ Member に戻す。Manager が勝手に規約外 base の PR を作らない。

## やってはいけないこと

- 同一スレッドで Manager のまま実装へ進まない。
- 依存 Issue があることを理由に stacked `feature -> feature` PR を作らない。
- project branch を飛ばして `feature -> main` PR を作らない。
