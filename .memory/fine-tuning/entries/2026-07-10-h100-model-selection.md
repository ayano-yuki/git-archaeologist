# H100 One-GPU Model Selection for Git Archaeologist

## Summary

2026-07-10時点では、H100 1枚のファインチューニング環境なら、まず `Qwen/Qwen3-14B` でパイプラインを確認し、その後 `Qwen/Qwen2.5-Coder-32B-Instruct` を本命候補として試すのがよい。Git Archaeologist はGitHub履歴、コード、レビュー、設計判断を扱うため、コード理解に強い32B級モデルが合いやすい。

ただし、モデル選定は変化が速い。実験当日は Hugging Face の model card、ライセンス、必要VRAM、Transformers対応バージョンを再確認する。

## Context

実際の学習環境は、高火力 VRT/24Core-240GB-H100x1、Ubuntu Server 24.04.2 LTS 64bit、SSD 2TB前後を想定している。GPUはH100 1枚と見なし、VRAMは80GB級である前提で考える。

このリポジトリの目的は、`react/react` のIssue、PR、Commit、Reviewなどを材料に、設計判断、原因分析、根拠引用、レビュー思考を説明できるモデルを作ること。GitHub履歴そのものはRAGで扱い、Fine-tuningでは推論様式を学ばせる。

## What Happened

H100 1枚で現実的に扱える候補として、次の順序を推奨した。

1. `Qwen/Qwen3-14B`
   - 最初の動作確認、データ形式確認、LoRA設定確認に向く。
   - 14.8B paramsで、32Bより試行錯誤が軽い。

2. `Qwen/Qwen2.5-Coder-32B-Instruct`
   - GitHub履歴、コードレビュー、設計判断の説明に向く本命候補。
   - 32.5B params、Apache-2.0、long-context対応。

3. `Qwen/Qwen3-32B`
   - 説明品質、日本語混じりの推論、一般的なreasoningを重視する場合の本命候補。
   - 32.8B params、Apache-2.0。

4. `meta-llama/Llama-3.1-8B-Instruct`
   - 軽量な比較用baseline。
   - 利用条件への同意やライセンス確認が必要。

## Beginner Explanation

ファインチューニングでは、最初から最大のモデルを選ぶと失敗原因を切り分けにくい。学習が遅い、メモリが足りない、データ形式が悪い、評価が悪い、という複数の問題が同時に起きるからです。

そのため、まず少し小さいモデルで「データを読めるか」「LoRAが刺さるか」「checkpointが出るか」「評価できるか」を確認する。ここで使うのが `Qwen/Qwen3-14B` の役割です。

次に、本命モデルで同じパイプラインを回す。Git Archaeologist はコードやレビューの文脈を扱うため、コード特化の `Qwen/Qwen2.5-Coder-32B-Instruct` が有力です。32B級は8Bより重いですが、H100 1枚ならQLoRAやLoRAで十分現実的な候補になります。

LoRAは、モデル全体を更新するのではなく、一部の小さな追加パラメータを学習する方法です。QLoRAは、モデル本体を4bit量子化してメモリ使用量を下げながらLoRAを学習する方法です。H100 1枚で32B級を試すなら、まずQLoRAが安全です。

## Why It Matters

モデル選定を間違えると、ファインチューニングの失敗が「モデルが悪い」のか「データが悪い」のか「学習設定が悪い」のか分からなくなる。

このプロジェクトでは、モデルにGitHub履歴を暗記させたいわけではない。必要なのは、RAGで渡された根拠を読み、事実と推論を分け、設計判断やリスクを説明する力です。したがって、コード理解と説明能力の両方を持つモデルを選ぶ必要がある。

## Actionable Guidance

- まず `Qwen/Qwen3-14B` でPoCを回す。
- 本命実験では `Qwen/Qwen2.5-Coder-32B-Instruct` を試す。
- 説明品質や日本語混じりの推論を重視する比較候補として `Qwen/Qwen3-32B` を試す。
- baselineには `Llama-3.1-8B-Instruct` など軽量モデルを使う。
- 32B級ではfull fine-tuningではなく、まずLoRAまたはQLoRAを使う。
- 実験当日に、モデルカードのライセンス、必要Transformersバージョン、context length、商用利用条件を確認する。
- `configs/model/base.yaml` は最初に次のようにする。

```yaml
model_name_or_path: Qwen/Qwen3-14B
trust_remote_code: false
torch_dtype: bfloat16
load_in_4bit: true
```

本命実験では次に切り替える。

```yaml
model_name_or_path: Qwen/Qwen2.5-Coder-32B-Instruct
trust_remote_code: false
torch_dtype: bfloat16
load_in_4bit: true
```

## Evidence

- `Qwen/Qwen2.5-Coder-32B-Instruct`: Apache-2.0、32.5B params、long-context 128K tokens、コード生成・コード推論・コード修正向けの説明がある。
  - https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct
- `Qwen/Qwen3-32B`: Apache-2.0、32.8B params、native 32K context、YaRNで131K tokens。
  - https://huggingface.co/Qwen/Qwen3-32B
- `Qwen/Qwen3-14B`: 14.8B params、native 32K context、YaRNで131K tokens。
  - https://huggingface.co/Qwen/Qwen3-14B
- `meta-llama/Llama-3.1-8B-Instruct`: 8B、128K context、baseline候補。利用条件とライセンス確認が必要。
  - https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct

## Open Questions

- 実際のH100のVRAM容量が80GBかどうかは、作業当日に確認する。
- `Qwen3-14B` と `Qwen2.5-Coder-32B-Instruct` のどちらが、GitHub履歴から設計判断を説明する評価で良いかは未検証。
- Thinking modeを持つQwen3系を使う場合、学習データに思考過程を含めるべきか、最終回答だけを含めるべきかは別途検証する。
