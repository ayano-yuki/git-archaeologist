# PR 作成前ゲート

Member Codex が pull request を作成する前に使う確認ゲート。

## 発火条件

次の操作前に停止する。

- `gh pr create`
- `gh pr create` を呼ぶ補助スクリプト
- GitHub API による PR 作成

## 提示する情報

Member Codex は次を人間に提示する。

- 関連 Issue 番号
- 現在の worktree パス
- 作業ブランチ
- PR の向き先ブランチ
- PR の階層関係が `main <- project` または `project <- feature` であること
- PR topology 判定: `feature -> project/<function-area>` または `project/<function-area> -> main` のどちらか
- 禁止形でないこと: `feature -> main`、`feature -> feature`、`project -> feature` ではないこと
- 実装概要
- 受け入れ条件との対応
- 実行したテストと結果
- 既知のリスクまたは未対応事項
- PR タイトル案
- PR 本文案
- `git push -u origin feature/<issue-number>-<short-title>` コマンド案
- `gh pr create` コマンド案

## 人間レビュー観点

人間に次を確認してもらう。

- 実装が Issue の設計とズレていない。
- PR の範囲が大きすぎない。
- テストが変更内容に対して十分である。
- 危険な変更が明示されている。
- PR の向き先が `main <- project` または `project <- feature` の隣接階層である。
- 依存 Issue があっても `feature -> feature` の stacked PR になっていない。
- PR タイトルが `[機能] PR内容（#issue番号）` 形式である。
- PR 本文に `- [https://github.com/ayano-yuki/ayano-yuki-pbi/issues/123](https://github.com/ayano-yuki/ayano-yuki-pbi/issues/123)` のように、Issue URL をラベルにも使うリンク形式が含まれている。

## 再開条件

人間が PR 作成を承認した後にだけ進める。設計ズレが見つかった場合は、実装または PR 案を修正してから再提示する。

PR topology が禁止形の場合は、人間承認があっても `gh pr create` を実行しない。正しい `project/<function-area>` branch へ作り直す方針を提示して停止する。
