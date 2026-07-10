# Raw GitHub Evidence To SFT Data

## Summary

GitHub の Issue、PR、Commit、Review をそのまま SFT に入れるのは避ける。raw evidence は事実を参照するための材料であり、SFT では「根拠をどう使って説明するか」という答え方を学ばせる。

## Context

`react/react` の GitHub API 収集結果を、Git Archaeologist 用の SFT JSONL に変換する作業。raw evidence は `data/raw/github/react-react/`、変換後の学習データは `data/processed/train.jsonl` と `validation.jsonl`。

## What Happened

`llm_tuning_lab.data.github_sft` を追加し、raw record を `messages` 形式へ変換する処理を実装した。生成される assistant 応答は、単一の GitHub record から断定的な結論を出さず、事実、推論、不確実性を分ける内容にした。

## Beginner Explanation

RAG は retrieval-augmented generation の略で、回答時に外部の事実を検索して参照する方法。SFT は supervised fine-tuning の略で、モデルに望ましい入力と出力のパターンを学ばせる方法。

GitHub 履歴には事実が多く含まれる。たとえば、PR のタイトル、Issue の本文、Commit message、Review comment など。ただし、それらをモデルに暗記させると、データが古くなったり、別リポジトリで間違った記憶を使ったりしやすい。事実は RAG で取り出し、SFT では「取り出した事実をどう慎重に説明するか」を学ばせる。

## Why It Matters

raw GitHub 履歴をそのまま学習すると、モデルは根拠の扱いよりも表面的な文言や古い事実を覚えやすい。Git Archaeologist の価値は暗記ではなく、履歴 evidence をもとに設計判断や変更理由を再構成する推論様式にある。

## Actionable Guidance

- `data/raw/` は RAG や変換処理の入力として扱う。
- SFT JSONL では `Facts`, `Inference`, `Uncertainty` のように役割を分ける。
- 単一の Issue や PR だけで「理由はこれ」と断定しない。
- 学習データには秘密情報、巨大ログ、private な履歴を入れない。
- 高品質な本番データでは、人間が期待回答をレビューしてから使う。

## Evidence

- 関連ファイル: `src/llm_tuning_lab/data/github_sft.py`
- 関連ファイル: `src/llm_tuning_lab/data/prepare.py`
- 関連コマンド: `uv run --system-certs --group dev python -m llm_tuning_lab.data.prepare --input data/raw/github/react-react --train-output data/processed/train.jsonl --validation-output data/processed/validation.jsonl --validation-ratio 0.2`
- 確認結果: raw 524件から SFT 524件を生成し、train 419件、validation 105件に分割した。

## Open Questions

現在の自動変換は PoC 用の土台であり、最終的な学習品質を保証するものではない。今後は、関連 PR、Issue、Commit、Review を束ねて、より文脈のある学習例にする必要がある。
