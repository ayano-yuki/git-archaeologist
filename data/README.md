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

## 注意

- 生データ、教師データ、モデル出力、評価ログは原則 Git に含めない。
- コミットする必要がある小さなサンプルは、個人情報、秘密情報、private repository 固有情報を除去してから追加する。
- モデル間でデータを混ぜない。共通データが必要な場合も、コピーまたは生成手順で再現できるようにする。

## 収集設定との関係

Repository ごとの収集範囲、対象 artifact、除外ルール、private 情報の扱いは `src/git_archaeologist/config/repositories/` の設定から参照する。`data/` 配下には、その設定で取得した実データや評価出力だけを置く。

収集に失敗した場合は、設定で定義されたエラー報告項目を使い、対象 Repository、artifact 種別、対象 ID、実行操作、エラー種別、エラーメッセージを人間へ連絡する。認証ヘッダー、token、秘密鍵などの値は報告や保存に含めない。

