# Benchmark-Based Eval Coverage

## Summary

Git Archaeologist の評価は、prediction 側に存在する行だけを採点してはいけない。benchmark 全件を基準にして、missing prediction を0点として扱う必要がある。そうしないと、簡単なケースだけを提出した run が高く見えてしまう。

## Context

EvidenceBundle と GoldCase ベースの SFT パイプラインを作った後、再レビューで `run_eval.py` の弱点が見つかった。以前の評価は prediction JSONL に含まれる record だけを反復していたため、benchmark に存在するが prediction に欠けているケースが summary へ反映されなかった。

## What Happened

`src/llm_tuning_lab/eval/run_eval.py` を benchmark 全件基準に変更した。prediction がない benchmark case は `status: missing` として `zero_metrics` を与える。重複ID、未知ID、coverage、benchmark件数、prediction件数、matched件数、missing件数も summary に出すようにした。

## Beginner Explanation

SFT は supervised fine-tuning の略で、期待する回答例からモデルの振る舞いを学ばせる方法。評価では、モデルが固定された問題セットにどれだけ答えられたかを測る。

もし評価スクリプトが「提出された回答だけ」を採点すると、難しい問題を未提出にするだけで平均点を上げられる。これはモデル性能ではなく、評価の抜け道を測っている状態になる。

benchmark は試験問題の全体、prediction は提出答案に近い。採点は提出答案の束ではなく、試験問題の全体を基準にする。

## Why It Matters

Git Archaeologist では、RAG-only、SFT-only、RAG+SFT などを比較する。coverage を見ない評価だと、ある方式だけが失敗したケースを出力しなかった場合でも、高く見える可能性がある。

missing prediction を0点にすると、評価結果が「回答できたケースだけの品質」ではなく「benchmark 全体への対応力」を表すようになる。

## Actionable Guidance

- 評価スクリプトは benchmark 全件を反復する。
- prediction が欠けた case は0点にする。
- duplicate ID と unknown ID は summary に記録する。
- summary には `benchmark_count`, `prediction_count`, `matched_count`, `missing_count`, `duplicate_count`, `unknown_count`, `coverage` を含める。
- モデル比較では、平均点だけでなく coverage も見る。

## Evidence

- 関連ファイル: `src/llm_tuning_lab/eval/run_eval.py`
- 関連ファイル: `src/llm_tuning_lab/eval/metrics.py`
- 関連テスト: `tests/test_run_eval.py`
- 関連コマンド: `uv run --system-certs pytest`
- 確認結果: 36 tests passed。

## Open Questions

missing prediction は一律0点にしたが、推論サーバー障害とモデルの回答不能を運用上どう区別するかは未設計。今後は prediction 生成側で failure reason を記録すると、評価とインフラ障害の切り分けがしやすくなる。
