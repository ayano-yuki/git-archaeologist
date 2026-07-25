# Answer Schema

MVP の回答は、根拠付き事実、推論、不足情報を分けて扱う。
生成 LLM の出力は `StructuredAnswer` として validation し、schema 違反時は安全な `insufficient_evidence` 応答へ落とす。

## 必須フィールド

- `verdict`: `explained`、`risk_found`、`no_risk_found`、`insufficient_evidence`。
- `confirmed_reasons`: Evidence に支えられた事実 claim。各 claim は citation を必須にする。
- `evidence`: Evidence Pack 内の引用元。`source_id`、`source_url`、`supports` を持つ。
- `inferences`: citation を参照できるが、事実 claim とは分けて表示する推論。
- `potential_risks`: 変更リスクの claim。
- `recommended_actions`: 推奨確認や次アクション。
- `missing_information`: 根拠不足、未取得 artifact、判断不能理由。
- `confidence`: `low`、`medium`、`high`。

## schema 違反時

schema 違反、未知 citation、citation なしの事実 claim は検出し、回答をそのまま表示しない。
代わりに `safe_schema_error` で `insufficient_evidence` 応答を作り、再生成または追加 Evidence 取得へ進める。
