# Linux SFT Runbook

## 目的

Linux の H100 環境で、`react/react` の GitHub 履歴を使った SFT パイプラインを1コマンドで起動するための手順です。

この手順は、依存同期、GitHub 履歴収集、SFT 用 JSONL 生成、データ検証、SFT 起動までをまとめます。CUDA、driver、bitsandbytes、容量、通信の実環境エラーは実機で確認します。

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

## 1コマンド実行

```bash
bash scripts/run_sft_linux.sh --preset react-react-qwen3-14b
```

このコマンドは次の順に実行します。

1. `uv sync --system-certs --extra train --group dev`
2. `react/react` の GitHub evidence を `data/raw/github/react-react/` に収集
3. raw evidence から `data/processed/train.jsonl` と `data/processed/validation.jsonl` を生成
4. 生成した JSONL を検証
5. `Qwen/Qwen3-14B` で LoRA SFT を起動

## 実行前に確認する

SFT 本体を回さずにコマンド列を確認します。

```bash
bash scripts/run_sft_linux.sh --dry-run --preset react-react-qwen3-14b
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
data/processed/train.jsonl         SFT train data
data/processed/validation.jsonl    SFT validation data
outputs/sft/react-react-qwen3-14b  学習ログと checkpoint
```

これらは大きくなりやすいため Git 管理しません。

## よくある確認点

- `uv` が入っているか。
- `GITHUB_TOKEN` が rate limit を避けるために設定されているか。
- `HF_HOME` が十分な容量のあるディスクを指しているか。
- `data/processed/train.jsonl` と `validation.jsonl` が空でないか。
- `configs/model/base.yaml` が `Qwen/Qwen3-14B` を指しているか。
- `outputs/sft/react-react-qwen3-14b` に書き込み権限があるか。

## 方針

GitHub 履歴そのものをモデルに暗記させるのではなく、raw evidence から「根拠を整理する」「事実と推論を分ける」「不確実性を明示する」会話形式のデータを作ります。事実検索は RAG に任せ、SFT では答え方と推論様式を学習させます。
