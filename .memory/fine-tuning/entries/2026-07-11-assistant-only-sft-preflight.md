# Assistant Only SFT And Preflight

## Summary

SFT では、学習させたい対象を明確にする必要がある。Git Archaeologist では user や system の文を暗記させたいのではなく、assistant の答え方、根拠の扱い方、不確実性の示し方を学ばせたい。そのため conversational `messages` を保持し、`assistant_only_loss: true` を使う方針にした。

## Context

Linux H100 環境で `Qwen/Qwen3-14B` を LoRA SFT するための実装点検。SFT 本体はまだ実行せず、ローカルで潰せる問題を先に潰した。

## What Happened

以前の実装では、`messages` を `tokenizer.apply_chat_template()` で `text` に変換してから `SFTTrainer` に渡していた。この形だと、assistant 応答だけでなく、system prompt、user prompt、evidence summary も次トークン予測の対象になりやすい。

修正後は、JSONL の `messages` を保持したまま TRL の `SFTTrainer` に渡し、`SFTConfig` で `assistant_only_loss: true` を設定する。さらに `--preflight-only` を追加し、GPU を使う前に train/validation の空ファイルや設定不足を検出できるようにした。

## Beginner Explanation

SFT は supervised fine-tuning の略で、入力に対して期待する出力を学ばせる方法。会話データでは、user は質問、assistant は答えを表す。

モデルに本当に学ばせたいのは多くの場合 assistant の答えである。user の質問文まで強く学ばせると、モデルは「どう答えるか」よりも「入力に出てきた文章を続ける」方向に寄りやすい。特に GitHub 履歴を扱う場合、Issue や PR の文面を暗記するのではなく、根拠をどう整理して説明するかを学ばせることが大切。

preflight は、学習を始める前の事前点検である。GPU を使う前に、ファイルが存在するか、空ではないか、設定が足りているかを確認する。

## Why It Matters

assistant 以外まで学習対象にすると、RAG で参照すべき事実をモデルが暗記しようとする危険がある。また、空の validation file を見逃すと、実機で学習を始めてから評価データがないことに気づく。H100 の時間を節約するためにも、GPU を使わない検証で落とせるものは先に落とす。

## Actionable Guidance

- SFT データは可能な限り `messages` 形式で保持する。
- `configs/train/sft.yaml` に `assistant_only_loss: true` を置く。
- SFT 前に `--preflight-only` を実行する。
- train/validation JSONL が空でないことを確認する。
- GitHub 履歴の事実は RAG に任せ、SFT では答え方と推論様式を学ばせる。

## Evidence

- 関連ファイル: `src/llm_tuning_lab/train/sft.py`
- 関連ファイル: `src/llm_tuning_lab/train/sft_runtime.py`
- 関連ファイル: `configs/train/sft.yaml`
- 関連コマンド: `uv run --system-certs --group dev python -m pytest`
- 確認結果: 21 tests passed.
- 関連コマンド: `uv run --system-certs --group dev python -m llm_tuning_lab.train.sft --model-config configs/model/base.yaml --data-config configs/data/react_react_sft.yaml --train-config configs/train/sft.yaml --lora-config configs/train/lora.yaml --train-file data/processed/train.jsonl --validation-file data/processed/validation.jsonl --output-dir outputs/sft/react-react-qwen3-14b --preflight-only`
- 確認結果: `OK: SFT configs and data files are ready.`

## Open Questions

実機で `Qwen/Qwen3-14B` の 4bit LoRA が期待どおり H100 に配置されるか、`eos_token: <|im_end|>` が今回の tokenizer と完全に一致するかは、実環境で最終確認する。
