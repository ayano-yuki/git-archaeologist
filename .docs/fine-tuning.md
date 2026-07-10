# Fine-tuning Guide

## 基本方針

ファインチューニングでは、モデルに「答え方」や「推論様式」を学ばせます。このリポジトリでは、GitHub履歴の事実そのものは RAG で参照し、Fine-tuning では根拠の使い方、設計判断の説明、原因分析、レビュー思考を学ばせる方針です。

## 1. 小さいPoCデータを作る

最初から大きなデータを使わず、`data/samples/` に小さな JSONL を作ります。

```json
{"messages":[{"role":"system","content":"You distinguish the proper noun React from the common verb react using context."},{"role":"user","content":"Should it be React or react?"},{"role":"assistant","content":"Use React when referring to the JavaScript library, and react when using the verb."}]}
```

PoCでは、人間が期待出力をすぐ判断できる題材を選びます。現在は `data/samples/react_react_poc.jsonl` を使っています。

## 2. GitHub履歴を収集する

Git Archaeologist では、GitHub履歴そのものをモデルに直接覚えさせません。まず `data/raw/` に raw evidence として保存し、RAG用インデックスやSFT用サンプルへ後段で変換します。

`react/react` を収集する入口:

```powershell
.\scripts\collect_react_github.ps1
```

少量で試す場合:

```powershell
.\scripts\collect_react_github.ps1 -MaxPages 1 -PerPage 10
```

GitHub APIのrate limitを避けるため、必要に応じて `GITHUB_TOKEN` を環境変数に設定します。

出力先:

```text
data/raw/github/react-react/
  issues.jsonl
  pulls.jsonl
  commits.jsonl
  issue_comments.jsonl
  pull_review_comments.jsonl
  pull_reviews.jsonl
  manifest.json
```

`data/raw/` はGit管理しません。収集した履歴をそのまま学習データとしてコミットしないでください。

## 3. データ形式を検証する

```powershell
.\scripts\validate_data.ps1 -Path data\samples\react_react_poc.jsonl
```

この検証では、各行が JSON object であること、`messages` があること、`user` と `assistant` が含まれることを確認します。

## 4. データ設定を差し替える

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

## 5. モデル設定を確認する

既定のモデル設定は `configs/model/base.yaml` です。

```yaml
model_name_or_path: Qwen/Qwen3-14B
trust_remote_code: false
torch_dtype: bfloat16
load_in_4bit: true
```

まず `Qwen/Qwen3-14B` でデータ形式、LoRA設定、checkpoint保存、評価の流れを確認します。本命実験では、同じ入口のまま `model_name_or_path` を `Qwen/Qwen2.5-Coder-32B-Instruct` などに切り替えます。

## 6. 学習を実行する

```powershell
.\scripts\train_sft.ps1 -DataConfig configs/data/poc.yaml
```

別ファイルを指定する場合:

```powershell
.\scripts\train_sft.ps1 -DataConfig configs/data/poc.yaml -TrainFile data\samples\your_sample.jsonl
```

Linux の H100 環境で `react/react` の収集、変換、検証、SFT 起動までをまとめて行う場合:

```bash
bash scripts/run_sft_linux.sh --preset react-react-qwen3-14b
```

SFT 本体を起動せず、事前に実行予定コマンドだけ確認する場合:

```bash
bash scripts/run_sft_linux.sh --dry-run --preset react-react-qwen3-14b
```

既に `data/raw/github/react-react/` がある場合は、収集を飛ばして変換と検証から始めます。

```bash
bash scripts/run_sft_linux.sh --skip-collect --preset react-react-qwen3-14b
```

## 6.5 実行前チェック

H100 で SFT を回す前に、GPU を使わずに潰せる問題を先に潰します。

```bash
uv run --system-certs --group dev python -m pytest
uv run --system-certs --group dev python -m llm_tuning_lab.run.sft_pipeline --dry-run --skip-collect --preset react-react-qwen3-14b --include-sync-command
uv run --system-certs --group dev python -m llm_tuning_lab.data.validate data/processed/train.jsonl
uv run --system-certs --group dev python -m llm_tuning_lab.data.validate data/processed/validation.jsonl
uv run --system-certs --group dev python -m llm_tuning_lab.train.sft --model-config configs/model/base.yaml --data-config configs/data/react_react_sft.yaml --train-config configs/train/sft.yaml --lora-config configs/train/lora.yaml --train-file data/processed/train.jsonl --validation-file data/processed/validation.jsonl --output-dir outputs/sft/react-react-qwen3-14b --preflight-only
```

確認すること:

- `data/processed/train.jsonl` と `validation.jsonl` が空ではない。
- 各行が `messages` 形式で、`user` と `assistant` を含む。
- `configs/model/base.yaml` が `Qwen/Qwen3-14B` を指している。
- `configs/train/sft.yaml` が `assistant_only_loss: true` を持っている。
- `outputs/sft/react-react-qwen3-14b` に書き込める。
- `HF_HOME` が十分な容量のあるディスクを指している。

SFT では conversational `messages` をなるべく保持します。`messages` を事前に1本の `text` へ潰すと、assistant の回答だけでなく user や system の文まで学習対象になりやすいためです。このリポジトリでは、根拠や質問を丸暗記させるのではなく、assistant の答え方、根拠の扱い方、不確実性の示し方を学ばせます。

## 7. 結果を保存する

学習ログや checkpoint は `outputs/`、adapter やモデル成果物は `models/` に置きます。これらは大きくなりやすいため、原則 Git 管理しません。

## 8. 知見をMemoryに残す

実験中に分かったことは `.memory/fine-tuning/entries/` に残します。

残すべき内容:

- 成功した小さい設定
- データ形式の失敗
- 学習が進まなかった原因
- 評価で見つかった問題
- 初学者が誤解しやすい点
- 次回同じ状況で確認すべきこと

新しいメモを書くときは `.memory/fine-tuning/templates/knowledge-note.md` を使います。
