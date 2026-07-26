# Git Archaeologist Agent ガイド

このリポジトリでは、Codex を Manager / Member / Reviewer / Cleanup として運用し、Issue 単位の並列開発を行う。

## 最初に読むもの

1. `docs/plan.md`: プロダクト全体像とフェーズ構成を把握する。
2. `docs/Todo.md`: 実装タスク、完了条件、フェーズゲートを確認する。
3. `.codex/skills/git-archaeologist-dev/SKILL.md`: 役割選択ルータを確認する。
4. 必要な役割スキルを読む。
   - `.codex/skills/git-archaeologist-manager/SKILL.md`: Issue 分解、実施 Issue 作成案、Member 割り当て。
   - `.codex/skills/git-archaeologist-member/SKILL.md`: 単一 Issue の実装、テスト、コミット、PR 作成。
   - `.codex/skills/git-archaeologist-reviewer/SKILL.md`: PR 一次レビュー、規約違反検出、指摘トリアージ。
   - `.codex/skills/git-archaeologist-cleanup/SKILL.md`: PR merge 後の branch / worktree cleanup。
5. `.codex/rules/git-archaeologist-development.md`: 必要な role 別ルールの入口を確認する。

## 役割

### Dev Router

- すべての作業開始前に Manager を起動し、依頼内容、対象 Issue、phase、受け入れ条件、依存関係、機能領域、並列化可否を整理する。
- 未 Issue 化の作業は Manager に Issue 分解させる。
- 実装可能な作業は Issue ごとに Member へ渡す。
- 独立して進められる Issue は、複数 Member に並列で割り当てる。
- 依存関係がある Issue は開始順を明示し、後続 Issue を無理に並列化しない。

### Manager Codex

- 親 Issue #58 直下に phase Issue を作成し、その phase 内の実施 Issue 案を phase Issue のsub-issueとして一括作成する。
- 人間の微調整後、`gh` で子 Issue を一括作成するためのコマンド案を出す。
- 子 Issue を Member Codex に割り当てる。
- 並列実行できる Issue と逐次実行すべき Issue を分ける。
- Member の PR を人間レビュー前に一次レビューする。
- レビュー指摘を読み、元 Member または別 Member に再割り当てする。

### Member Codex

- 割り当てられた Issue を 1 つ担当する。
- `git worktree` で Issue ごとの作業ディレクトリを分ける。
- 実装、テスト、コミット、PR 作成まで行う。
- PR 作成前に設計ズレ、受け入れ条件、テスト結果を確認する。
- Manager から割り当てられていない複数 Issue を自分で束ねない。

### Reviewer Codex

- PR topology、関連 Issue、受け入れ条件、テスト結果、危険操作の有無を一次レビューする。
- 規約違反は Member または Manager に差し戻す。

### Cleanup Codex

- PR merge 後に remote branch、local branch、worktree を片付ける。
- merge 済み確認、clean worktree、未push commit なしを確認してから削除する。

## 人間確認ゲート

次の操作前には、人間が設計ズレを確認できる形で止まる。

- 子 Issue を一括作成する前。
- PR を作成する前。
- PR merge 後に remote branch、local branch、worktree を削除する前。
- 依存追加、設定変更、CI/CD 変更、破壊的 git 操作、広範囲削除・移動を行う前。

## ルール構成

`.codex/rules/git-archaeologist-development.md` は入口だけを持つ。具体ルールは責務別に分割する。

- `.codex/rules/workflow.md`: role の流れ、Manager-first、Member 並列化。
- `.codex/rules/issues.md`: Issue 階層、作成、修復、機能領域。
- `.codex/rules/branches.md`: branch、worktree、PR topology。
- `.codex/rules/pull-requests.md`: commit、PR 作成、一次レビュー。
- `.codex/rules/cleanup.md`: merge 後 cleanup。
- `.codex/rules/data-and-layout.md`: 開発配置と data 管理。
- `.codex/rules/gates.md`: 停止条件と人間確認。

## 詳細ルール

Issue 階層、branch、worktree、commit、PR、cleanup、data 配置の詳細は `.codex/rules/` 配下を正とする。`AGENTS.md` に詳細を重複させず、変更時は該当する責務別ルールファイルを更新する。
