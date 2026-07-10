# Data Replacement PoC Should Start Small

## Summary

ファインチューニング環境のPoCでは、最初から大きな実データを使わず、小さく意図が明確なデータで入口を確認する。今回のPoCでは、`React` と `react` の使い分けを題材にした JSONL を使い、データを差し替えるだけで同じ学習入口に流せることを確認する構成にした。

## Context

このリポジトリでは `configs/data/poc.yaml` の `train_file` を差し替えることで、SFT用データを切り替える。PoCデータは `data/samples/react_react_poc.jsonl` に置いている。

## What Happened

最初に「React / react」を React UI のPoCだと誤解したが、実際には学習に使うデータの題材だった。そこで画面アプリではなく、`React` という固有名詞と `react` という動詞を文脈で区別する小さな学習データに修正した。

## Beginner Explanation

ファインチューニングでは、モデルに「何を学ばせたいのか」がデータに強く現れる。PoCの段階では、巨大なデータを入れるよりも、期待する振る舞いが数行で分かる小さなデータを使う方がよい。

たとえば `React` と `react` の違いは単純に見えるが、モデルには文脈判断が必要になる。UIライブラリ名なら `React`、英語の動詞なら `react` になる。このような小さい題材は、データ形式、検証、学習入口、出力確認を安全に試すのに向いている。

## Why It Matters

最初から大きなデータで試すと、失敗したときに原因が分かりにくい。データ形式が悪いのか、学習コードが悪いのか、モデル設定が悪いのか、環境が悪いのかを切り分けられない。

小さなPoCデータなら、問題が起きたときに原因を追いやすい。学習環境が正しくつながった後で、実データに差し替える方が安全。

## Actionable Guidance

- 新しい学習タスクを始めるときは、まず `data/samples/` に10件未満の小さなJSONLを作る。
- `scripts/validate_data.ps1` で `messages` 形式を検証する。
- `configs/data/*.yaml` の `train_file` を差し替えて同じ入口で動かす。
- うまく動いたら、`data/processed/` の本番用データに切り替える。
- PoCでは、期待する正解が人間にすぐ分かる題材を選ぶ。

## Evidence

- 関連ファイル: `data/samples/react_react_poc.jsonl`
- 関連ファイル: `configs/data/poc.yaml`
- 関連コマンド: `.\scripts\validate_data.ps1 -Path data\samples\react_react_poc.jsonl`

## Open Questions

このPoCデータで実際に小さなモデルを学習したとき、どの程度のステップ数で期待する振る舞いが出るかは未検証。
