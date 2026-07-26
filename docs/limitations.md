# Phase5 制約と非対応範囲

Git Archaeologist は、取得済みの GitHub / Git 履歴とローカル索引を根拠に、実装理由、変更リスク、障害、行・条件分岐の由来を説明する。履歴に残っていない意思決定や外部会話を復元するものではない。

この文書は、実装で保証していることと保証していないことを分け、回答不能になる代表条件と確認方法をまとめる。

## 保証していること

- 取得済みの Commit、PR、Issue、Review、CI、Revert、Diff、blame、索引済み symbol / line history を根拠候補として扱う。
- 回答の主要な主張は Evidence Pack と citation ID へ接続し、根拠が不足する場合は不足情報または不明を返す。
- 観測できた事実、システムによる推論、根拠不足を分けて扱う。
- 現在の実装は、ファイル・関数、PR変更リスク、障害/Revert、行・条件分岐の分析を同じイベント基盤と Evidence Pack へ集約する。
- 最新PRは質問時の Current Change Context として扱える。ただし、過去履歴は最後に同期された索引時点に依存する。

## 保証していないこと

- Repository や GitHub に残っていない外部会話、口頭決定、チャット、会議メモを推測で補わない。
- 削除済み branch、削除済み artifact、権限不足で読めない private data、保存前に redaction された内容は復元しない。
- shallow clone、欠落した tag / branch / CI log、force-push で到達不能になった commit を完全な履歴として扱わない。
- 対応言語外や parser fallback の symbol / condition 追跡について、一意の由来を断定しない。
- 因果関係は、明示リンク、同一 commit、PR/Issue 参照、CI head SHA などの観測根拠がある場合に強く扱う。時刻や同一ファイルだけの一致は推定であり、原因として断定しない。
- モデル学習に Repository 固有の事実を記憶させること、外部収集を自動で開始すること、本物のモデル学習をこの文書更新で保証することはしない。

## 回答不能となる代表条件と確認方法

| 条件 | 起きること | 確認方法 |
| --- | --- | --- |
| 対象の PR / Issue / Review / CI log が未収集または取得不能 | 根拠不足として回答を棄権するか、追加同期を促す | `uv --system-certs run python -m git_archaeologist.ops.sync --status` で repository、index version、synced_at、watermarks を確認する |
| 質問対象が shallow clone や欠落履歴の範囲にある | blame、rename、lineage の起点が途中で止まる | 対象 repository の clone depth、対象 commit の到達性、`git log` で履歴が追えるか確認する |
| branch / tag / artifact が削除済み | 削除後の情報を復元できず、不明または部分根拠として扱う | Raw Archive、manifest、source URL、GitHub 上の artifact 有無を確認する |
| 外部会話や口頭決定だけに理由がある | 履歴から確認できる事実だけを返し、理由は不明とする | PR本文、Issue本文、Review、commit message に根拠があるか確認する |
| 対応言語外、parser fallback、複雑な rename / copy / refactor | symbol や条件分岐の候補が複数になり、断定しない | `docs/parser-policy.md` と候補一覧、lineage confidence を確認する |
| CI log が長大、redaction済み、権限不足 | failure signature や stack frame が欠ける | Raw Archive の redaction 結果、CI artifact 取得権限、failure event の抽出結果を確認する |
| Current Change Context の取得に失敗 | 最新PRの差分を前提にした変更リスク判定を行わない | `gh` 認証、対象 PR URL、network / certificate failure のログを確認する |

## トラブルシューティング入口

- Setup: [README.md のセットアップ確認](../README.md#セットアップ確認)で、storage layout、`gh` 認証、runtime profile、初回索引手順を確認する。
- Sync: [README.md の同期状態確認](../README.md#同期状態確認)で、status と manual sync plan を確認する。外部収集は明示実行まで進めない。
- Data protection: [docs/Todo.md のデータ保護と削除手順](./Todo.md#52-ローカル運用と配布)で、保存場所、削除境界、backup / deletion 手順の担当範囲を確認する。
- Regression: [docs/Todo.md の全機能回帰評価](./Todo.md#54-最終品質保証)で、regression suite、比較レポート、合否判定の担当範囲を確認する。
- Parser / language scope: [docs/parser-policy.md](./parser-policy.md)で、対応言語、fallback、未対応時の動作を確認する。

## 利用時の読み方

回答が「不明」「根拠不足」「追加同期が必要」と返した場合、それは実装が外部事実を復元できなかったという意味ではなく、現在の取得済み根拠だけでは主要主張を支えられないという意味である。確認方法をたどっても根拠が見つからない場合、システムは推測で理由を補わない。
