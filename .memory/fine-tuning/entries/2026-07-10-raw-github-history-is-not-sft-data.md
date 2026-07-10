# Raw GitHub History Is Not SFT Data

## Summary

GitHubから収集したIssue、PR、Commit、Reviewは、そのままSFTデータにしない。まず `data/raw/` に raw evidence として保存し、RAG用の知識ソースや、後段の変換処理でSFTサンプルへ加工する。

## Context

`react/react` を対象に、Git Archaeologist 用のデータ収集スクリプトを追加した。収集対象は GitHub API の Issue、PR、Commit、Issue comment、PR review comment、PR review である。

## What Happened

収集スクリプトは raw JSON を `.jsonl` に包んで `data/raw/github/react-react/` に出力する設計にした。これは学習用 `messages` JSONL とは別物であり、`scripts/validate_data.ps1` の対象ではない。

## Beginner Explanation

SFTは、モデルに「こういう入力にはこう答えてほしい」という振る舞いを教える方法です。一方、GitHubのIssueやPRは事実や履歴の集まりです。履歴をそのまま学習させると、モデルが事実を暗記しようとしたり、古い情報と新しい情報を混ぜたりする可能性があります。

Git Archaeologist の方針では、事実知識はRAGで参照します。RAGは、回答時に必要な文書を検索してモデルへ渡す仕組みです。Fine-tuningでは、検索された根拠をどう読み、どう説明し、どこからが推論なのかを分ける力を学ばせます。

## Why It Matters

raw履歴とSFTデータを混ぜると、データの責務が曖昧になる。収集、検索、学習、評価のどこで問題が起きたのか切り分けにくくなる。

raw履歴をまず保存しておけば、後からRAG用に分割したり、設計判断の説明例だけを抽出してSFT用 `messages` に変換したりできる。

## Actionable Guidance

- GitHub APIの結果は `data/raw/github/<repo>/` に保存する。
- raw JSONLをそのまま `configs/data/*.yaml` の `train_file` にしない。
- SFTに使う前に、根拠、質問、期待回答が明確な `messages` 形式へ変換する。
- 秘密情報やprivate repositoryの履歴は収集前に扱いを確認する。
- 収集件数は最初は `-MaxPages 1 -PerPage 10` のように小さく試す。

## Evidence

- 関連ファイル: `src/llm_tuning_lab/collect/github.py`
- 関連ファイル: `configs/collect/react_react.yaml`
- 関連コマンド: `.\scripts\collect_react_github.ps1 -MaxPages 1 -PerPage 10`

## Open Questions

raw GitHub履歴から、どの単位でSFT用の「設計判断」「原因分析」「レビュー思考」サンプルに変換するのが最も効果的かは、次の実験で検証する。
