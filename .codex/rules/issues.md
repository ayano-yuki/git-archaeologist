# Issue ルール

## Issue 階層

- 親 PBI Issue は `ayano-yuki/ayano-yuki-pbi#58` とする。
- 親 PBI #58 直下には、原則として phase まとめ Issue だけを置く。
- phase Issue は `【git-archaeologist 】 phaseNN` 形式にする。
- 実施 Issue は対応する phase Issue の GitHub sub-issue として作成する。
- 子 Issue タイトルは `【git-archaeologist 】 <内容>` 形式にする。

## 作成と修復

- 子 Issue は Manager Codex が一括で案を作り、人間が微調整してから作成する。
- phase Issue 作成時は `gh issue create --parent 58` を使う。
- 実施 Issue 作成時は `gh issue create --parent <phase-issue-number>` を使う。
- 既存の実施 Issue が親 PBI #58 直下にある場合は、`gh issue edit <issue-number> --parent <phase-issue-number>` で修復する。
- Issue 作成または修復後は、親 Issue #58 の `subIssues`、phase Issue の `subIssues`、または子 Issue の `parent` を確認する。

## 子 Issue の必須項目

- タイトル
- 親 PBI #58 との sub-issue 関係
- 背景
- 実装内容
- 受け入れ条件
- 触る想定ファイル
- テスト方針
- 依存 Issue
- 優先度
- Member への作業指示
- PR 作成時の注意点
- 機能領域

## 機能領域

`project/<function-area>` は次の固定値から選ぶ。

- `collector`: GitHub / git 履歴収集、Raw Archive、認証・権限検査。
- `normalizer`: 共通イベント、Normalizer、Event Graph、関係生成。
- `search`: Code / Symbol Index、Hybrid Search、Target Resolver。
- `rag`: Evidence Pack、Reranker、Answer / Judge LLM、Citation Verifier。
- `chat`: Input Interpreter、チャット UI / API、会話状態。
- `evaluation`: 評価セット、品質指標、回帰評価、性能計測。
