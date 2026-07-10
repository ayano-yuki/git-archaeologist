# Fine-tuning Guide

## 基本方針

ファインチューニングでは、モデルに「答え方」や「推論様式」を学ばせます。このリポジトリでは、GitHub履歴の事実そのものは RAG で参照し、Fine-tuning では根拠の使い方、設計判断の説明、原因分析、レビュー思考を学ばせる方針です。

## 1. 小さいPoCデータを作る

最初から大きなデータを使わず、`data/samples/` に小さな JSONL を作ります。

```json
{"messages":[{"role":"system","content":"You distinguish the proper noun React from the common verb react using context."},{"role":"user","content":"Should it be React or react?"},{"role":"assistant","content":"Use React when referring to the JavaScript library, and react when using the verb."}]}
```

PoCでは、人間が期待出力をすぐ判断できる題材を選びます。現在は `data/samples/react_react_poc.jsonl` を使っています。

## 2. データ形式を検証する

```powershell
.\scripts\validate_data.ps1 -Path data\samples\react_react_poc.jsonl
```

この検証では、各行が JSON object であること、`messages` があること、`user` と `assistant` が含まれることを確認します。

## 3. データ設定を差し替える

PoC用設定は `configs/data/poc.yaml` です。

```yaml
train_file: data/samples/react_react_poc.jsonl
validation_file:
format: messages
required_roles:
  - user
  - assistant
```

別のデータで試す場合は `train_file` を差し替えるか、実行時に `-TrainFile` を指定します。

## 4. 学習を実行する

```powershell
.\scripts\train_sft.ps1 -DataConfig configs/data/poc.yaml
```

別ファイルを指定する場合:

```powershell
.\scripts\train_sft.ps1 -DataConfig configs/data/poc.yaml -TrainFile data\samples\your_sample.jsonl
```

## 5. 結果を保存する

学習ログや checkpoint は `outputs/`、adapter やモデル成果物は `models/` に置きます。これらは大きくなりやすいため、原則 Git 管理しません。

## 6. 知見をMemoryに残す

実験中に分かったことは `.memory/fine-tuning/entries/` に残します。

残すべき内容:

- 成功した小さい設定
- データ形式の失敗
- 学習が進まなかった原因
- 評価で見つかった問題
- 初学者が誤解しやすい点
- 次回同じ状況で確認すべきこと

新しいメモを書くときは `.memory/fine-tuning/templates/knowledge-note.md` を使います。
