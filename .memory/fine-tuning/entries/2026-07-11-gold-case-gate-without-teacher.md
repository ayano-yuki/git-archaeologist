# Gold Case Gate Without Teacher Generation

## Summary

Git Archaeologist 用の SFT では、教師モデルで assistant 回答を自動生成しない方針にした。代わりに、人間作成または外部作成済みの gold case を検証し、`review_status: approved` の case だけを学習データへ materialize する。これは、低品質なテンプレート回答や未検証の推論を SFT で強化しないためのゲートになる。

## Context

GitHub raw record 1件を定型回答へ変換する PoC から、Issue / PR / Commit / Review / Diff / CI を束ねた `EvidenceBundle` 単位の学習基盤へ移行した。対象コードは `src/llm_tuning_lab/data/bundles.py` と `src/llm_tuning_lab/data/gold_cases.py`。

## What Happened

実装では、教師モデルによる回答生成を入れなかった。`GoldCase` は `bundle_id`, `question`, `answer`, `facts`, `timeline`, `inference`, `uncertainty`, `citations`, `review_status` を持つ。検証では、存在しない evidence ID の引用、引用なし facts、時系列逆転、空の uncertainty、単一証拠だけの断定回答を reject する。

## Beginner Explanation

SFT は supervised fine-tuning の略で、入力と期待出力の例からモデルの振る舞いを学ばせる方法。期待出力が弱いと、モデルは弱い答え方を学ぶ。

教師モデル生成は、強いモデルに回答案を作らせる方法。ただし、生成された回答が根拠に合っているとは限らない。Git Archaeologist では、引用した evidence ID が本当に入力にあるか、時系列が逆転していないか、証拠不足なのに断定していないかが重要になる。

そのため、今回の方針では「回答を自動生成する」より先に「承認済み回答だけを通す」ことを優先した。gold case は、SFT に使ってよいと判断済みの正解例という意味で使っている。

## Why It Matters

低品質な自己生成回答を大量に学習しても、Git Archaeologist の能力は伸びにくい。モデルが覚えるのは、設計判断の復元ではなく、慎重そうな定型文かもしれない。

承認済み gold case を gate にすると、学習前にデータ品質の責任点がはっきりする。RAG に任せる事実知識と、SFT で学ばせる推論様式も分けやすくなる。

## Actionable Guidance

- raw GitHub record を直接 SFT にしない。
- まず `llm_tuning_lab.data.bundles` で `EvidenceBundle` を作る。
- SFT 用回答は `data/interim/gold_cases/*.jsonl` に置く。
- 学習前に `llm_tuning_lab.data.gold_cases validate` を通す。
- `review_status: approved` ではない case を通常の SFT に混ぜない。
- 教師生成を後で追加する場合も、同じ gold case validation を通してから採用する。

## Evidence

- 関連ファイル: `src/llm_tuning_lab/data/bundles.py`
- 関連ファイル: `src/llm_tuning_lab/data/gold_cases.py`
- 関連ファイル: `src/llm_tuning_lab/run/sft_pipeline.py`
- 関連コマンド: `uv run --system-certs python -m llm_tuning_lab.data.gold_cases validate --bundles data/interim/bundles/react-react.jsonl --gold-cases data/interim/gold_cases/react-react.jsonl`
- 検証結果: `uv run --system-certs pytest` で 30 tests passed。

## Open Questions

gold case を何件用意すれば、RAG-only と RAG-plus-SFT の差を安定して測れるかはまだ未検証。教師生成を将来使う場合も、人間レビューの基準と自動検査の範囲を先に決める必要がある。
