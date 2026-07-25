---
name: git-archaeologist-dev
description: Git Archaeologist リポジトリ専用の Codex Manager / Member 並列開発を支援する。親 PBI から子 Issue を分解する、Issue 一括作成案を準備する、Member に作業を割り当てる、git worktree で実装する、コミットと PR を作成する、Manager 一次レビューを行う、PR レビュー指摘を再割り当てする場合に使う。
---

# Git Archaeologist Dev

## 概要

Git Archaeologist を Issue 駆動で並列開発するための Skill。人間はレビューと設計ズレ確認を担当し、Codex は Manager / Member として動く。

## 最初に読むもの

作業前に次を読む。

- `docs/plan.md`: プロダクト方針とフェーズ構成。
- `docs/Todo.md`: 実装タスク、完了条件、フェーズゲート。
- `.codex/skills/git-archaeologist-dev/references/orchestration.md`: Manager / Member の全体運用。
- `.codex/rules/git-archaeologist-development.md`: ブランチ、コミット、PR、停止条件のルール。
- `data/README.md`: 学習・評価・実験用データのモデル別配置ルール。
- `.codex/hooks/issue-create-gate.md`: 子 Issue 作成前ゲート。
- `.codex/hooks/pr-create-gate.md`: PR 作成前ゲート。
- `.codex/hooks/dangerous-operation-gate.md`: 危険操作前ゲート。

## 役割の選び方

- 作業計画、子 Issue 作成、Member 割り当て、PR 一次レビュー、レビュー指摘トリアージを求められたら Manager として動く。
- 単一 Issue の実装、テスト、コミット、PR 作成を求められたら Member として動く。
- 役割が曖昧な場合は、依頼内容から推定し、どの役割で動くかを明示する。

## Manager ワークフロー

1. 親 Issue `ayano-yuki/ayano-yuki-pbi#58`、`docs/plan.md`、`docs/Todo.md` を読む。
2. `.codex/orchestration/templates/child-issue.md` を使って子 Issue 案を作る。
3. 各 Issue を `collector`、`normalizer`、`search`、`rag`、`chat`、`evaluation` のいずれかへ分類する。
4. `.codex/orchestration/templates/issue-batch-plan.md` を使って一括作成計画を作る。
5. `gh issue create --parent 58` の前に停止し、人間へ設計ズレ確認を依頼する。
6. 承認後、`.codex/skills/git-archaeologist-dev/references/gh-commands.md` のコマンド例をもとに Issue 作成を準備または実行する。子 Issue は必ず親 PBI #58 の GitHub sub-issue として作成する。
7. 作成済み Issue が sub-issue になっていない場合は、`gh issue edit <issue-number> --parent 58` で修復する。
8. Issue 作成または修復後、親 Issue #58 の `subIssues` または子 Issue の `parent` を確認する。
9. 子 Issue を Member Codex の worktree へ割り当てる。承認済みの並列作業は、各 Issue のコミット、push、PR 作成までを完了条件にする。
10. 最終報告前に、push 済み feature ブランチと open PR の対応を確認する。PR がない push 済み feature ブランチは未完了として扱い、PR 作成まで進める。
11. 人間レビュー前に、PR の範囲、受け入れ条件、明らかな問題、テスト、規約違反を一次レビューする。
12. レビュー指摘が来たら、元 Member または別 Member へ再割り当てする。

## Member ワークフロー

1. 割り当て Issue とリポジトリルールを読む。
2. Issue 専用の `git worktree` を作る。
3. Issue の範囲だけを実装する。
4. Issue のテスト方針に沿って検証する。
5. `.codex/rules/git-archaeologist-development.md` の形式でコミットする。
6. `.codex/orchestration/templates/pr.md` を使って PR 本文を作る。
7. `gh pr create` の前に停止し、人間へ設計ズレ確認を依頼する。
8. 承認後、feature ブランチを push し、対応する `project/<function-area>` を base に PR を作成する。push だけで停止しない。
9. PR URL を取得して報告する。push 済みで PR URL がない状態は未完了として扱う。
10. PR 作成後、作業済み worktree が clean で push 済みであることを確認し、不要になった worktree を削除する。

## 人間確認ゲート

次の操作前には停止する。

- 子 Issue の一括作成または sub-issue 紐付けの修復。
- PR 作成。
- 依存関係の追加。
- CI/CD、GitHub Actions、認証、秘密情報、データ保存先、ロードマップの変更。
- 破壊的 git 操作または破壊的ファイル操作。

停止時には、実行したい操作、理由、影響範囲、コマンド案、sub-issue 確認方法、戻し方または代替案を提示する。

人間が明示的に PR 作成を依頼または承認した場合は、PR 作成前ゲートを通過したものとして扱い、feature ブランチの push と PR 作成まで完了する。Member に作業を投げる場合も、承認済みなら最終成果物を「コミット、push、PR 作成」まで含めて指示する。

並列で複数 Issue を進める場合も同じ完了条件を適用する。Manager は最終報告前に `gh pr list` などで push 済み feature ブランチに対応する PR があることを確認し、漏れがあれば PR を作成してから報告する。

PR 作成まで完了した worktree は、`git status --short --branch` で clean かつ upstream 追跡済みであることを確認してから `git worktree remove <path>` で片付ける。未コミット差分、未 push commit、レビュー対応予定が残る worktree は削除せず、残す理由を報告する。

1 ファイルあたりの変更量は、おおむね 400 行から 600 行に収まるようにする。600 行を超えそうな場合は、Issue 分割、責務ごとのファイル分割、テスト fixture の分離を検討し、やむを得ず超える場合は PR 本文と Manager 一次レビューで理由を明記する。

## ブランチと PR ルール

ブランチ階層は次を使う。

```text
main
phase/1-mvp
project/<function-area>
feature/<issue-number>-<short-title>
```

PR の向き先は隣接階層だけに限定する。

- `project/<function-area>` から `main`。
- `feature/<issue-number>-<short-title>` から対応する `project/<function-area>`。
- `feature` から `main`、`feature` から別 `feature`、`project` から `feature` への PR は作らない。

PR タイトルは次の形式にする。

```text
[機能] PR内容（#issue番号）
```

PR 本文には次を含める。

```text
- [issue] #123
```

## 開発配置

- Python 開発は `uv` を使う。
- 証明書エラーで `uv run` が失敗する環境では `uv --system-certs run ...` を使う。
- コードは `src/` 配下に置く。
- パッケージコードは `src/git_archaeologist/` 配下に置く。
- 学習・評価・実験用データは `data/<model-name>/` 配下に置く。
- モデル別データ配置は `data/README.md` に従う。

## 参照

- `.codex/skills/git-archaeologist-dev/references/orchestration.md`: 全体運用。
- `.codex/skills/git-archaeologist-dev/references/gh-commands.md`: コマンドテンプレート。
- `.agents/manager.md`: Manager の詳細チェックリスト。
- `.agents/member.md`: Member の詳細チェックリスト。
