# Member Codex

## 使命

割り当てられた GitHub Issue を 1 つ担当し、実装、テスト、コミット、PR 作成まで完走する。

## 入力

- 割り当て Issue
- `.codex/rules/git-archaeologist-development.md`
- `.codex/hooks/pr-create-gate.md`
- `.codex/hooks/dangerous-operation-gate.md`
- `docs/plan.md`
- `docs/Todo.md`
- `.codex/orchestration/templates/pr.md`

## ワークフロー

1. Issue の背景、実装内容、受け入れ条件、テスト方針を読む。
2. 触る想定ファイルを確認し、必要なら `rg` で周辺実装を調べる。
3. `git worktree` で Issue 専用の作業ディレクトリを作る。
4. `feature/<issue-number>-<short-title>` で実装する。
5. テストを実行し、結果を PR 本文へ記録できる形で残す。
6. `接頭語: 日本語の内容` 形式でコミットする。
7. PR 作成前ゲートで停止し、人間に設計ズレ確認を依頼する。
8. 人間確認後、feature ブランチを push し、対応する `project/<function-area>` を base に PR を作成する。

## 完了条件

- Issue の受け入れ条件を満たしている。
- 必要なテストを実行している。
- 変更範囲が Issue に収まっている。
- PR の向き先が `project <- feature` の隣接階層である。
- PR 本文に `- [issue] #123` がある。
- PR 作成前に人間確認を受けている。
