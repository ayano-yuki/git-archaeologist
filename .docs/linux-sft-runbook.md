# Linux SFT Runbook

## 目的

Linux の H100 環境で、`react/react` の GitHub 履歴を使った SFT パイプラインを1コマンドで起動するための手順です。

この手順は、依存同期、GitHub 履歴収集、evidence bundle 生成、gold case 検証、SFT 用 JSONL 生成、評価、SFT 起動までをまとめます。CUDA、driver、bitsandbytes、容量、通信の実環境エラーは実機で確認します。

## 事前準備

```bash
git clone <this-repository>
cd llm-tuning-lab
```

必要に応じて環境変数を設定します。

```bash
export GITHUB_TOKEN=...
export HF_TOKEN=...
export HF_HOME=/mnt/large-cache/huggingface
```

`GITHUB_TOKEN` は GitHub API の rate limit を避けるために使います。`HF_TOKEN` は Hugging Face の gated model や private model を使う場合に必要です。`HF_HOME` は大きなモデルをシステムディスクではなく大容量ディスクへ置くために使います。

SFT 用の回答は教師モデルで生成しません。事前に、人間作成または外部作成済みでレビュー済みの gold case を用意します。

```text
data/interim/gold_cases/react-react.jsonl
```

各 gold case は `bundle_id`, `question`, `answer`, `facts`, `timeline`, `inference`, `uncertainty`, `citations`, `review_status` を持ち、SFT に使うものは `review_status: approved` にします。

## 1コマンド実行

```bash
bash scripts/run_sft_linux.sh --preset react-react-qwen3-14b
```

このコマンドは次の順に実行します。

1. `uv sync --system-certs --extra train --group dev`
2. `react/react` の GitHub evidence を `data/raw/github/react-react/` に収集
3. raw evidence から `data/interim/bundles/react-react.jsonl` を生成
4. `data/interim/gold_cases/react-react.jsonl` を検証
5. 承認済み gold case だけを train / validation / test と benchmark に変換
6. 生成した SFT JSONL を検証
7. benchmark に対する baseline 予測を採点
8. `--preflight-only` で SFT 設定と空データを検証
9. `Qwen/Qwen3-14B` で LoRA SFT を起動
10. benchmark に対する post-train 予測を採点

## 実行前に確認する

SFT 本体を回さずにコマンド列を確認します。

```bash
bash scripts/run_sft_linux.sh --dry-run --preset react-react-qwen3-14b
```

GPU を使わずに SFT 設定だけを検証する場合:

```bash
uv run --system-certs --group dev python -m llm_tuning_lab.train.sft \
  --model-config configs/model/base.yaml \
  --data-config configs/data/react_react_sft.yaml \
  --train-config configs/train/sft.yaml \
  --lora-config configs/train/lora.yaml \
  --train-file data/processed/train.jsonl \
  --validation-file data/processed/validation.jsonl \
  --output-dir outputs/sft/react-react-qwen3-14b \
  --preflight-only
```

すでに `data/raw/github/react-react/` がある場合は、GitHub API 収集を飛ばせます。

```bash
bash scripts/run_sft_linux.sh --skip-collect --preset react-react-qwen3-14b
```

社内プロキシなどで TLS 検証が壊れる場合だけ、次を使います。

```bash
bash scripts/run_sft_linux.sh --insecure-ssl --preset react-react-qwen3-14b
```

`--insecure-ssl` は通信の安全性を下げるため、信頼できるネットワーク上の検証用途に限定します。

## 出力先

```text
data/raw/github/react-react/       GitHub API から収集した raw evidence
data/interim/bundles/react-react.jsonl       調査ケース単位の evidence bundle
data/interim/gold_cases/react-react.jsonl    承認済み回答を含む gold case
data/processed/train.jsonl         SFT train data
data/processed/validation.jsonl    SFT validation data
data/processed/test.jsonl          SFT test data
evals/benchmarks/react-react.jsonl 固定 holdout benchmark
evals/results/*.json               評価結果
outputs/sft/react-react-qwen3-14b  学習ログと checkpoint
```

これらは大きくなりやすいため Git 管理しません。

## よくある確認点

- `uv` が入っているか。
- `GITHUB_TOKEN` が rate limit を避けるために設定されているか。
- `HF_HOME` が十分な容量のあるディスクを指しているか。
- `data/interim/gold_cases/react-react.jsonl` が存在し、承認済み case を含むか。
- `data/processed/train.jsonl`、`validation.jsonl`、`test.jsonl` が空でないか。
- `configs/model/base.yaml` が `Qwen/Qwen3-14B` を指しているか。
- `configs/train/sft.yaml` で `assistant_only_loss: true` になっているか。
- `outputs/sft/react-react-qwen3-14b` に書き込み権限があるか。

## 方針

GitHub 履歴そのものをモデルに暗記させるのではなく、raw evidence から調査ケース単位の `EvidenceBundle` を作り、承認済み `GoldCase` だけを SFT に使います。事実検索は RAG に任せ、SFT では答え方と推論様式を学習させます。

学習時は conversational `messages` を保持し、`assistant_only_loss: true` で assistant 応答を主な学習対象にします。user や system の文面までそのまま予測対象にすると、モデルが質問文や根拠文の丸暗記に寄りやすくなります。
