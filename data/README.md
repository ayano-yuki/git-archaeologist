# 学習用データ配置ルール

`data/` には、学習・評価・実験・本番動作確認に使うデータを保存する。サーバー上で同じ repository checkout から再現できるように、`data/` 配下は runtime raw archive、processed data、Evidence Pack、run output、SFT / eval データを含めて Git 管理対象にする。

Git 管理対象にする前提のため、`data/` には secret、token、認証ヘッダー、private key、private repository 由来 artifact、未 redaction の機微情報を置かない。private 情報を含む可能性があるデータは `data/` へ保存する前に除去または redaction する。

## 基本構造

モデルごとにフォルダーを分ける。

```text
data/
  <model-name>/
    raw/
    processed/
    evidence-packs/
    sft/
    eval/
    runs/
```

## モデル名

`<model-name>` には、ファイルシステムで扱いやすい名前を使う。Hugging Face などの `org/model` 形式は `/` を `--` に置き換える。

例:

```text
Qwen/Qwen2.5-Coder-7B-Instruct -> data/Qwen--Qwen2.5-Coder-7B-Instruct/
```

## サブディレクトリ

- `raw/`: 取得した元データ。加工前の GitHub / git 由来データ。
- `processed/`: 正規化済みデータ、中間生成物。
- `evidence-packs/`: 回答や評価に使う Evidence Pack。
- `sft/`: SFT 用の教師データ。
- `eval/`: 評価データ、期待結果、評価レポート。
- `runs/`: 実験ごとの出力、ログ、メトリクス。

## MVP 評価データ

MVP の入力形式と品質目標は `src/git_archaeologist/evaluation/mvp_contracts.py` の
`mvp-input-quality-v1` を基準にする。評価対象の履歴は
`react/react` 由来の GitHub / git 履歴を使う前提とし、対象 Repository
固有の事実はモデルへ記憶させず、収集済みデータと Evidence Pack から参照する。

評価データは、使うモデルごとに次のように置く。

```text
data/
  <model-name>/
    eval/
      mvp-input-quality/
        input-examples.jsonl
        quality-targets.json
        evaluation-run.md
```

- `input-examples.jsonl`: PR URL + ファイル名または関数名、コード断片 + 自然言語質問の正常例、曖昧な例、不正な例。
- `quality-targets.json`: 対象解決精度、根拠検索再現率、引用整合率、根拠のない主張率、リスク警告の適合率、回答時間の暫定目標。
- `evaluation-run.md`: 評価前に固定した contract version、dataset version、evaluator version、実行日時、結果、変更しなかった基準。

品質目標は評価前に固定する。評価結果を見たあとで都合よく基準値、対象例、採点方法を変更しない。変更が必要な場合は、新しい contract version と変更理由を先に記録してから次の評価を実行する。

## 注意

- `data/` 配下の生データ、モデル出力、実験ログ、runtime output は Git に含める。
- 個人情報、秘密情報、private repository 固有情報、未redactの生artifactは `data/` に置かない。
- モデル間でデータを混ぜない。共通データが必要な場合も、コピーまたは生成手順で再現できるようにする。

## FT / SFT データ方針

Fine-tuning / SFT は、Repository 固有事実をモデルへ記憶させる目的では使わない。MVP では RAG とプロンプト改善を先に行い、それでも繰り返し残る回答規律の失敗を改善する場合だけ導入する。

学習してよい内容は次に限定する。

- Evidence Pack の読み方と、根拠が支える事実・推論・不明の分離。
- Evidence Pack にない内容を断言しない抑制規律。
- 主張を支える citation の選び方。
- 実装理由説明、変更リスク判定、レビュー判断の回答形式。
- 根拠がある場合の原因分析、時系列整理、レビュー上の判断手順。

学習してはいけない内容は次のとおり。

- Commit、PR、Issue、Review、CI などの Repository 固有事実そのもの。
- Evidence Pack なしで特定 Repository の履歴を答える closed-book QA。
- 生の GitHub / git artifact をそのまま正解として与えるデータ。
- secret、token、認証ヘッダー、private key、private repository 固有情報。
- Evidence Pack で支えられていない断言、引用不整合、事実と推論の混同を含む理想回答。

初期データソースは `react/react` から収集した履歴とする。収集範囲、artifact 種別、除外ルールは `src/git_archaeologist/config/repositories/react_react.json` の Repository 設定に従う。

## SFT レコード形式

SFT 用データは `data/<model-name>/sft/` に保存し、質問、対象、Evidence Pack、理想回答を 1 レコードにまとめる。評価用データと評価レポートは `data/<model-name>/eval/` に保存する。どちらもモデルごとに `data/<model-name>/` 配下へ閉じ込め、別モデルのデータと混ぜない。

最小形式は次の構造にする。

```json
{
  "schema_version": 1,
  "record_id": "sft-react-react-0001",
  "source_repository": "react/react",
  "split": "train",
  "question": "Why did this review require an additional guard?",
  "target": {
    "repository_id": "react/react",
    "target_type": "pull_request",
    "artifact_ids": ["pr-123"]
  },
  "evidence_pack": {
    "pack_id": "ep-react-react-0001",
    "evidence_items": [
      {
        "source_id": "review-1",
        "artifact_kind": "review_comment",
        "source_url": "https://github.com/react/react/pull/123#discussion_r1",
        "excerpt": "Reviewer text or normalized excerpt."
      }
    ]
  },
  "ideal_answer": {
    "answer": "Evidence-backed structured answer.",
    "citations": ["review-1"],
    "unsupported_claims": [],
    "confidence": "medium"
  },
  "labels": {
    "task": "review_judgment",
    "requires_abstention": false
  }
}
```

`split` は `train`、`validation`、`test` のいずれかにする。同じ PR、Issue、Review thread、または同じ意思決定に属する artifact は複数 split へ跨がせない。時系列評価が必要な場合は、学習期間より後の履歴を `eval/` に置き、SFT 前後で同じ評価を再実行できるようにする。

## 収集エラー時の人間連絡

収集時に次のエラーが発生した場合は、人間へ連絡する。

- `auth_or_permission`: `gh` 認証、Repository、PR、Issue、Review、Actions 権限不足。
- `rate_limit_or_timeout`: API rate limit、timeout、一時的な GitHub / git 取得失敗。
- `partial_or_interrupted_collection`: ページング途中の中断、cursor 不整合、再開不能。
- `artifact_missing_or_deleted`: 対象 artifact の削除、移動、取得時点での 404。
- `schema_or_parse_error`: GitHub API、git、正規化済みデータの schema 差異や parse 失敗。
- `redaction_or_secret_detection`: secret らしき値を検出し、保存または教師データ化を止めた場合。
- `storage_integrity_error`: hash 不一致、重複 ID、書き込み失敗、壊れた中間生成物。

報告には、`repository_id`、`artifact_kind`、`target`、`operation`、`error_type`、`error_message`、`source_url`、`retry_count` を含める。`raw_token`、`authorization_header`、`secret_value`、`private_key` は報告にも保存にも含めない。

## 記憶漏洩テスト

SFT を実施する場合は、closed-book 記憶漏洩テストを `data/<model-name>/eval/` に置く。これは Evidence Pack を空または無関係にした質問を与え、モデルが学習時に見た Repository 固有事実を根拠なしに答えないことを確認する評価である。

closed-book 評価ケースでは、`evidence_pack.evidence_items` を空にし、期待結果を `unknown` にする。合格条件は、回答が「Evidence Pack からは不明」と扱い、PR 番号、Commit SHA、作者、時系列、判断理由などを根拠なしに断言しないこと。学習期間より後の履歴にも同じ形式の評価を作り、単なる暗記だけでなく汎化時の根拠外断言も検出する。

## 収集設定との関係

Repository ごとの収集範囲、対象 artifact、除外ルール、private 情報の扱いは `src/git_archaeologist/config/repositories/` の設定から参照する。`data/` 配下には、その設定で取得した実データや評価出力だけを置く。

収集に失敗した場合は、設定で定義されたエラー報告項目を使い、対象 Repository、artifact 種別、対象 ID、実行操作、エラー種別、エラーメッセージを人間へ連絡する。認証ヘッダー、token、秘密鍵などの値は報告や保存に含めない。

