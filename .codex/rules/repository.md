# LLM Tuning Lab Rules

このリポジトリは Git Archaeologist 用の LLM ファインチューニング実験基盤です。

- 再現可能性を優先し、実験条件は `configs/` に残す。
- 再利用する処理は `src/llm_tuning_lab/` に置く。
- 実行用の薄い入口は `scripts/` に置く。
- Git 管理するデータは `data/samples/` の小さく安全なサンプルだけにする。
- `data/raw/`, `data/interim/`, `data/processed/`, `outputs/`, `models/`, `evals/results/` は原則 Git 管理しない。
- 学習前に JSONL 形式と必須フィールドを検証する。
- checkpoint、adapter、merged model、評価結果の大量出力をコミットしない。
- 手書きファイルは500行以下に保ち、責務分割を意識する。生成された lockfile は例外。
- Python の依存管理と実行は `uv sync --system-certs` / `uv run --system-certs` を使う。
- ファインチューニングに関する知見、注意点、失敗、うまくいく事例が発生したら `.memory/fine-tuning/` に残す。
- Memory は初学者に説明するつもりで、背景、観測事実、重要性、次に取る行動を分けて詳しく書く。
- 変更時は、必要に応じて `tests/` に小さな検証を追加する。

コミット時の標準手順:

- ユーザーがコミット、コミット分割、変更の確定を依頼したら、最終報告前に必ず `post-implementation-retrospective` スキルを使う。
- 振り返りでは `git status`、変更ファイル、直近コミット、実行した検証を確認し、同じ指示を次回も繰り返さないための改善点を探す。
- 改善候補として、Skills、`.codex/rules/`、`AGENTS.md`、hooks、docs、templates、`.memory/fine-tuning/` を見直す。
- ファインチューニングの知見や初学者向けに残すべき判断は、`fine-tuning-memory-writer` を使って `.memory/fine-tuning/` へ記録する。
- 変更の意図が複数ある場合は semantic commit splitter の考え方で分割し、プロダクト変更と振り返り由来の支援ファイル変更は可能な範囲で別コミットにする。
- 広いプロセス変更を黙って追加しない。ユーザーが明示した振り返り改善、または承認された提案だけを実装する。

Git Archaeologist の方針:

- GitHub 履歴そのものをモデルに記憶させない。
- Commit、PR、Issue、Review、Release Note、CI、blame などの事実知識は RAG で扱う。
- Fine-tuning では、設計判断、原因分析、根拠引用、障害分析、レビュー思考、暗黙知の説明方法を学習対象にする。
- 回答では根拠と推論を分け、不確実性を明示する。
