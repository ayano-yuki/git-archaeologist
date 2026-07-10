# Deterministic Content Metrics Are Not Judges

## Summary

Git Archaeologist の評価に、fact recall、timeline event recall、answer similarity、inference similarity を追加した。これらは、形式と citation ID だけで高得点を取る抜け道を減らすための決定的な近似指標である。ただし、LLM judge や人間評価の代替ではなく、意味評価の下限チェックとして扱う。

## Context

`src/llm_tuning_lab/eval/metrics.py` に、外部モデルへ依存しない content metrics を追加した。固定 benchmark で再現できることを優先し、token overlap と event matching による近似評価を採用した。

## What Happened

評価に以下の指標を追加した。

- `fact_precision` / `fact_recall`
- `fact_citation_precision` / `fact_citation_recall`
- `timeline_event_precision` / `timeline_event_recall`
- `timeline_date_precision` / `timeline_date_recall`
- `answer_similarity`
- `inference_similarity`
- `unsupported_claim_count`

また、`run_eval` に `--min-answer-similarity`, `--min-fact-recall`, `--min-timeline-event-recall` などの threshold option を追加した。

## Beginner Explanation

SFT は supervised fine-tuning の略で、期待する回答例からモデルの振る舞いを学ばせる方法。評価では、モデルの回答が期待値にどれだけ近いかを測る。

今回追加した指標は、回答文の主要な単語やイベントが GoldCase とどれくらい重なるかを見る。これは完全な意味理解ではない。たとえば、同じ意味を別の言い方で正しく説明した回答が低く出ることもあるし、似た単語を並べただけの回答が高めに出ることもある。

それでも、JSON形式、citation ID、timeline順序だけを見るよりは強い。少なくとも、answer や inference が GoldCase と全く違う場合に気づきやすくなる。

## Why It Matters

Git Archaeologist の目的は、Git履歴から設計理由や因果関係を説明すること。形式だけ整った回答を高く評価すると、モデルが「正しそうなJSON」を出すだけで改善したように見える。

決定的な近似指標は、CI や smoke test で使いやすい。一方で、能力向上を強く主張するには、LLM judge、人間評価、citation support判定などを追加する必要がある。

## Actionable Guidance

- 近似content metricsは、最低限の品質ゲートとして使う。
- `answer_similarity` や `fact_recall` が低い run は、形式が良くても改善したと判断しない。
- 対外的な主張では、これらの指標だけに依存しない。
- 小さな固定benchmarkでは、人間評価やLLM judgeを併用する。
- 指標名を読むときは「意味そのもの」ではなく「GoldCaseとの語彙・イベント一致」と解釈する。

## Evidence

- 関連ファイル: `src/llm_tuning_lab/eval/metrics.py`
- 関連ファイル: `src/llm_tuning_lab/eval/run_eval.py`
- 関連テスト: `tests/test_metrics.py`
- 関連テスト: `tests/test_run_eval.py`
- 関連コマンド: `uv run --system-certs pytest`
- 確認結果: 40 tests passed。

## Open Questions

どの threshold が実験に妥当かは、実際の GoldCase と予測結果を見て調整する必要がある。将来的には、factごとの citation support、contradiction detection、LLM judge、人間評価の併用を検討する。
