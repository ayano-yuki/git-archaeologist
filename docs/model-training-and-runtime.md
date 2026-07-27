# 学習とモデル起動

Git Archaeologist は、Repository 固有の事実をモデルに記憶させず、RAG の Evidence Pack を根拠として Answer / Judge LLM に回答させる。SFT / QLoRA は、根拠外の断言、引用不整合、事実と推論の混同など、回答規律の失敗を減らす目的に限定する。

この文書は、ローカル環境で学習 readiness を確認し、QLoRA adapter を作成し、学習後の評価とモデル利用入口を確認するための手順をまとめる。

## 前提

- Python 実行は `uv` を使う。
- 証明書エラーを避けるため、基本形は `uv --system-certs run ...` とする。
- 学習対象の Answer / Judge LLM は `Qwen/Qwen2.5-Coder-7B-Instruct`。
- QLoRA adapter の出力先は `data/Qwen--Qwen2.5-Coder-7B-Instruct/models/answer-discipline-qlora/`。
- SFT 実行計画は `data/baseline-rag/sft/answer-discipline/lora-training-plan.json`。
- `data/` 配下へ置くデータは、secret、token、認証ヘッダー、private key、未 redaction の private artifact を含めない。

## 1. ローカル実行条件を確認する

まず、外部サービスや重い学習を動かさずに runtime profile を確認する。

```powershell
uv --system-certs run python -m git_archaeologist.evaluation.runtime_profile
```

確認する主な項目:

- `selected_models`: Embedding、Reranker、Answer / Judge LLM の固定候補。
- `constraint_checks`: RAM、GPU / VRAM を含む実行可否。
- Answer / Judge LLM が `ready` でない場合は、CPU / 低VRAM実行として性能計測後に採否を決める。

ローカル運用全体の setup preflight は次で確認する。

```powershell
uv --system-certs run python -m git_archaeologist.ops.setup --dry-run
```

GitHub access を確認しないローカル-only確認では次を使う。

```powershell
uv --system-certs run python -m git_archaeologist.ops.setup --dry-run --skip-github-access
```

## 2. 学習依存関係を入れる

QLoRA を実行する場合だけ training extra を同期する。

```powershell
uv sync --extra training
```

この extra は `accelerate`、`bitsandbytes`、`datasets`、`peft`、`torch`、`transformers` を含む。GPU、CUDA、ドライバ、モデルダウンロードの失敗は環境依存なので、次の smoke で早めに検出する。

## 3. 学習前 smoke を実行する

標準の system smoke は、runtime profile、SFT plan、既存の安定化 smoke を確認する。

```powershell
uv --system-certs run python -m git_archaeologist.evaluation.system_smoke
```

training extra の import まで必須にする場合は次を使う。

```powershell
uv --system-certs run --extra training python -m git_archaeologist.evaluation.system_smoke --require-training-dependencies
```

本番収集データ、SFT plan、dataset、実行コマンド hint をまとめて確認する。

```powershell
uv --system-certs run python -m git_archaeologist.evaluation.production_training
```

training dependencies も readiness 条件に含める場合:

```powershell
uv --system-certs run --extra training python -m git_archaeologist.evaluation.production_training --require-training-dependencies
```

## 4. SFT dry-run を確認する

dry-run は重い学習 runtime を起動せず、plan、dataset、runtime制約、optional dependencies を検証する。

```powershell
uv --system-certs run --extra training python -m git_archaeologist.evaluation.train_sft --dry-run
```

見るべき項目:

- `status`: `sft_dry_run_passed`。
- `should_train`: plan が学習対象として有効か。
- `record_count` / `split_counts`: SFT dataset の件数。
- `output_dir`: adapter 出力先。
- `execute_ready`: 本番学習へ進める状態か。

## 5. モデルロードを最小確認する

サーバーやGPU上で、実際のモデルロード、4bit量子化、LoRA設定、Trainer 入口まで確認する最小実行は `--max-steps 1` を付ける。

```powershell
uv --system-certs run --extra training python -m git_archaeologist.evaluation.train_sft --execute --max-steps 1
```

データ量をさらに絞って load path だけ早く確認したい場合は `--dataset-limit` を併用できる。

```powershell
uv --system-certs run --extra training python -m git_archaeologist.evaluation.train_sft --execute --max-steps 1 --dataset-limit 8
```

この実行は `AutoTokenizer.from_pretrained` と `AutoModelForCausalLM.from_pretrained` を呼ぶため、モデル未取得環境ではダウンロードやキャッシュアクセスが発生する。

## 6. 本番 QLoRA を実行する

dry-run、training dependency smoke、1 step smoke が通ったあと、`--max-steps` を外して実行する。

```powershell
uv --system-certs run --extra training python -m git_archaeologist.evaluation.train_sft --execute
```

実行後、adapter と tokenizer は次へ保存される。

```text
data/Qwen--Qwen2.5-Coder-7B-Instruct/models/answer-discipline-qlora/
```

主要成果物:

- `adapter_config.json`
- `adapter_model.safetensors`
- `training-run-summary.json`
- `tokenizer_config.json`
- `tokenizer.json`

## 7. 学習後評価を実行する

adapter 成果物、training summary、closed-book 記憶漏洩契約、baseline / prompt / SFT 比較を確認する。

```powershell
uv --system-certs run python -m git_archaeologist.evaluation.post_sft_evaluation
```

既定の出力先:

```text
data/Qwen--Qwen2.5-Coder-7B-Instruct/eval/post-sft/answer-discipline-post-sft-report.json
```

`status` が `post_sft_evaluation_passed` でない場合、adapter 欠落、closed-book 漏洩、評価指標 regression のいずれかを先に解消する。

## 8. モデルの利用入口を確認する

外部サービスや実モデルを使わない deterministic なチャットデモは次で起動できる。

```powershell
uv --system-certs run python -m git_archaeologist.demo_chat
```

このデモは `git_archaeologist.chat.chat_flow.run_chat_flow` を通し、Input Interpreter、Target Resolver、Evidence Retriever、Answer Generator、Citation Verifier の接続形を確認するためのもの。実運用では、ここへ実際の Target Resolver、Evidence Retriever、Answer / Judge LLM backend、Citation Verifier backend を渡す。

現在のリポジトリには、常駐型のモデルサーバー CLI は用意していない。モデルを「起動する」確認としては、次の二つを使い分ける。

- 実行条件の確認: `git_archaeologist.evaluation.runtime_profile`
- 実モデルロードの確認: `git_archaeologist.evaluation.train_sft --execute --max-steps 1`

学習済み adapter を使う backend を接続する場合は、base model と adapter path を同じ model version として扱い、回答ログや cache key へ残す。

```text
base_model: Qwen/Qwen2.5-Coder-7B-Instruct
adapter: data/Qwen--Qwen2.5-Coder-7B-Instruct/models/answer-discipline-qlora/
model_version: Qwen2.5-Coder-7B-Instruct+answer-discipline-qlora
```

## 9. 失敗時の確認先

- setup が落ちる: `uv --system-certs run python -m git_archaeologist.ops.setup --dry-run`
- 同期状態が古い: `uv --system-certs run python -m git_archaeologist.ops.sync --status`
- training extra が足りない: `uv sync --extra training`
- dataset / plan が不正: `uv --system-certs run --extra training python -m git_archaeologist.evaluation.train_sft --dry-run`
- adapter 評価が落ちる: `uv --system-certs run python -m git_archaeologist.evaluation.post_sft_evaluation`
- データ保護を確認する: `uv --system-certs run python -m git_archaeologist.ops.data_protection --inventory`

データ配置の詳細は `../data/README.md`、モデル制約と性能計測は `./runtime-profile.md`、利用上の制約は `./limitations.md` を参照する。
