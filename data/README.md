# 学習用データ配置ルール

`data/` には、学習・評価・実験に使うローカルデータを保存する。Repository 固有の履歴や教師データは大きくなりやすく、private 情報を含む可能性があるため、原則として Git にコミットしない。

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

MVP の入力形式と品質目標は `src/git_archaeologist/mvp_contracts.py` の
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

- 生データ、教師データ、モデル出力、評価ログは原則 Git に含めない。
- コミットする必要がある小さなサンプルは、個人情報、秘密情報、private repository 固有情報を除去してから追加する。
- モデル間でデータを混ぜない。共通データが必要な場合も、コピーまたは生成手順で再現できるようにする。

