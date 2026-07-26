---
name: git-archaeologist-dev
description: "Git Archaeologist リポジトリの開発ロール選択用ルータ。使う場面: 作業開始前に Manager で依頼内容・Issue・依存関係・並列化可否を整理し、並列実行できる作業を Issue ごとに Member へ分配したいとき、または Manager / Member / Reviewer / Cleanup のどれを使うか曖昧なとき。Issue分解は git-archaeologist-manager、単一Issue実装は git-archaeologist-member、PR一次レビューは git-archaeologist-reviewer、merge後後始末は git-archaeologist-cleanup を使う。"
---

# Git Archaeologist Dev Router

## 基本方針

`git-archaeologist-dev` は実作業を抱え込まない。依頼を受けたら最初に Manager で作業内容を整理し、その結果に応じて Member / Reviewer / Cleanup へ明示的に引き渡す。

## 作業開始フロー

1. `git-archaeologist-manager` として、依頼内容、対象 Issue、phase、受け入れ条件、依存関係、機能領域を整理する。
2. 未 Issue 化の作業があれば、Manager が Issue 分解案を作り、人間確認ゲートへ進む。
3. 既存 Issue の実装依頼なら、Manager が対象 Issue を読み、並列化できる単位か確認する。
4. 独立して進められる Issue は、Issue ごとに `git-archaeologist-member` へ分配する。
5. 依存関係がある Issue は順序を明示し、先行 Issue の PR が作られるまで後続 Member を開始しない。
6. PR 作成後は `git-archaeologist-reviewer` で一次レビューする。
7. PR merge 後の branch / worktree 削除は `git-archaeologist-cleanup` に渡す。

## 役割選択

- 入口整理、Issue 分解、一括 Issue 作成案、Member 割り当て: `git-archaeologist-manager`
- 単一 Issue の実装、テスト、コミット、PR 作成: `git-archaeologist-member`
- PR 一次レビュー、PR topology 検査、レビュー指摘整理: `git-archaeologist-reviewer`
- merge 後の remote/local branch、worktree 削除: `git-archaeologist-cleanup`

## 共通で読むもの

- `docs/plan.md`
- `docs/Todo.md`
- `.codex/rules/git-archaeologist-development.md`

## 必要時だけ読む reference

- ルーティング手順で迷う場合: `references/orchestration.md`
- `gh` コマンド形を確認する場合: `references/gh-commands.md`

## 並列化の判断

並列 Member 起動してよい条件:

- 各 Issue の受け入れ条件が独立している。
- 触る主要ファイルまたは責務境界が衝突しない。
- 依存 Issue がない、または依存順が明確で先行作業だけを開始できる。
- 各 Issue の `project/<function-area>` base branch が存在し、古くない。

並列化せず Manager に戻す条件:

- Issue の粒度が大きすぎる。
- 複数 Issue が同じファイルを広く触り、競合が高い。
- base branch、親子 Issue、受け入れ条件、依存関係が不明。
- ユーザー依頼に実装、レビュー、cleanup が混在し、順序が曖昧。

## 絶対ルール

- Manager のまま実装へ進まない。実装は Member として開始を明示する。
- Member は 1 Issue だけを担当する。
- feature PR は必ず `feature/<issue-number>-<short-title> -> project/<function-area>`。
- project PR は必ず `project/<function-area> -> main`。
- `feature -> main` と `feature -> feature` は作らない。
- 依存 Issue があっても stacked `feature -> feature` PR は作らない。
- PR merge 後の branch / worktree 削除は Cleanup として行う。

## 迷った場合

ユーザーへ短く確認する。特に次は停止する。

- 対応 project branch が存在しない。
- PR base/head が規約に合わない。
- merge 済みでない branch の削除を求められた。
- 並列化の独立性を説明できない。
