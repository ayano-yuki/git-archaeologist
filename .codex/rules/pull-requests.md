# Pull Request ルール

## コミット

コミットメッセージは `接頭語: 日本語の内容` 形式にする。

推奨接頭語:

- `feat`: 機能追加
- `fix`: 不具合修正
- `test`: テスト追加・修正
- `docs`: ドキュメント
- `refactor`: 振る舞いを変えない整理
- `chore`: 設定・雑務

## PR 作成

- PR タイトルは `[機能] PR内容（#issue番号）` とする。
- PR 本文には関連 Issue を `- [https://github.com/ayano-yuki/ayano-yuki-pbi/issues/123](https://github.com/ayano-yuki/ayano-yuki-pbi/issues/123)` のように、Issue URL をラベルにも使うリンク形式で書く。
- PR 本文には受け入れ条件、テスト結果、Manager 一次レビューの観点を含める。
- PR 作成前に、受け入れ条件、テスト結果、設計ズレの有無をまとめて人間確認を受ける。
- 人間が PR 作成を依頼または承認済みの場合は、feature branch の push だけで止めず、PR URL を取得するまで進める。

## 一次レビュー

- PR 作成後、人間レビュー前に Reviewer Codex が一次レビューする。
- Reviewer は PR title、body、関連 Issue、受け入れ条件、テスト結果、危険操作の有無を確認する。
- PR topology 違反は重大指摘にする。
