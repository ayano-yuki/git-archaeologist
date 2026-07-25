# Codex オーケストレーション

このディレクトリは、Git Archaeologist の Issue 駆動並列開発を Codex Manager / Member で回すための運用資材を置く。

## 基本フロー

1. Manager Codex が親 Issue `ayano-yuki/ayano-yuki-pbi#58` と `docs/Todo.md` を読む。
2. Manager Codex が子 Issue 案を一括作成する。
3. 人間が子 Issue 案を微調整する。
4. Manager Codex が `gh` で子 Issue を一括作成するためのコマンド案を出す。
5. Manager Codex が Issue を Member Codex に割り当てる。
6. Member Codex が `git worktree` で Issue ごとの作業ディレクトリを作る。
7. Member Codex が実装、テスト、コミットを行う。
8. Member Codex が PR 作成前ゲートで停止する。
9. 人間が設計ズレを確認する。
10. Member Codex が PR を作成する。
11. Manager Codex が一次レビューする。
12. 人間が最終レビューし、必要なら Manager Codex が指摘を再割り当てする。

## テンプレート

- `templates/child-issue.md`: 子 Issue 本文テンプレート。
- `templates/pr.md`: PR 本文テンプレート。
- `templates/issue-batch-plan.md`: 子 Issue 一括作成前の確認テンプレート。

## Codex 実行用ファイル

- `.codex/rules/git-archaeologist-development.md`: ブランチ、コミット、PR、停止条件のルール。
- `.codex/hooks/issue-create-gate.md`: 子 Issue 作成前ゲート。
- `.codex/hooks/pr-create-gate.md`: PR 作成前ゲート。
- `.codex/hooks/dangerous-operation-gate.md`: 危険操作前ゲート。
- `.codex/skills/git-archaeologist-dev/references/gh-commands.md`: `gh` と `git worktree` のコマンドテンプレート。
