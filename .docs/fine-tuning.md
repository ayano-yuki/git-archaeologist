# Fine-tuning Guide

## 基本方針

ファインチューニングでは、モデルに「答え方」や「推論様式」を学ばせます。このリポジトリでは、GitHub履歴の事実そのものは RAG で参照し、Fine-tuning では根拠の使い方、設計判断の説明、原因分析、レビュー思考を学ばせる方針です。

手法の分類、SFT / LoRA / QLoRA / DPO / RAFT / GRPO などの違いは `.docs/fine-tuning-types.md` にまとめています。

## 1. 小さいPoCデータを作る

最初から大きなデータを使わず、`data/samples/` に小さな JSONL を作ります。

```json
{"messages":[{"role":"system","content":"You distinguish the proper noun React from the common verb react using context."},{"role":"user","content":"Should it be React or react?"},{"role":"assistant","content":"Use React when referring to the JavaScript library, and react when using the verb."}]}
```

PoCでは、人間が期待出力をすぐ判断できる題材を選びます。現在は `data/samples/react_react_poc.jsonl` を使っています。

## 2. GitHub履歴を収集する

Git Archaeologist では、GitHub履歴そのものをモデルに直接覚えさせません。まず `data/raw/` に raw evidence として保存し、RAG用インデックスやSFT用サンプルへ後段で変換します。

`react/react` を収集する入口:

```powershell
.\scripts\collect_react_github.ps1
```

少量で試す場合:

```powershell
.\scripts\collect_react_github.ps1 -MaxPages 1 -PerPage 10
```

GitHub APIのrate limitを避けるため、必要に応じて `GITHUB_TOKEN` を環境変数に設定します。

出力先:

```text
data/raw/github/react-react/
  issues.jsonl
  pulls.jsonl
  commits.jsonl
  issue_comments.jsonl
  pull_review_comments.jsonl
  pull_reviews.jsonl
  manifest.json
```

`data/raw/` はGit管理しません。収集した履歴をそのまま学習データとしてコミットしないでください。

## 3. Evidence bundle と gold case を作る

Git Archaeologist 用の本命データでは、raw record 1件をそのまま SFT 例にしません。Issue、PR、Commit、Review、Diff、CI を調査ケース単位の `EvidenceBundle` にまとめます。

```bash
uv run --system-certs python -m llm_tuning_lab.data.bundles \
  --input data/raw/github/react-react \
  --output data/interim/bundles/react-react.jsonl \
  --min-evidence-per-bundle 3
```

SFT 用の assistant 回答は教師モデルで生成しません。人間作成または外部作成済みの gold case を `data/interim/gold_cases/react-react.jsonl` に置き、SFT に使う行は `review_status: approved` にします。

gold case は最低限、次の情報を持ちます。`review_status: approved` の case では、`reviewer_id`, `reviewed_at`, `review_revision`, `bundle_hash`, `evidence_hash` も必須です。hashは、レビュー時点の bundle と evidence が学習時に差し替わっていないことを確認するために使います。

```json
{"bundle_id":"...","question":"Why was this design chosen?","answer":"...","facts":[{"text":"...","citations":["evidence-id"]}],"timeline":[{"date":"2026-01-01T00:00:00Z","text":"...","citations":["evidence-id"]}],"inference":"...","uncertainty":"...","citations":["evidence-id"],"review_status":"approved","reviewer_id":"reviewer-1","reviewed_at":"2026-01-02T00:00:00Z","review_revision":"1","bundle_hash":"...","evidence_hash":"..."}
```

検証と materialize:

```bash
uv run --system-certs python -m llm_tuning_lab.data.gold_cases validate \
  --bundles data/interim/bundles/react-react.jsonl \
  --gold-cases data/interim/gold_cases/react-react.jsonl

uv run --system-certs python -m llm_tuning_lab.data.gold_cases materialize \
  --bundles data/interim/bundles/react-react.jsonl \
  --gold-cases data/interim/gold_cases/react-react.jsonl \
  --train-output data/processed/train.jsonl \
  --validation-output data/processed/validation.jsonl \
  --test-output data/processed/test.jsonl \
  --benchmark-output evals/benchmarks/react-react.jsonl \
  --validation-ratio 0.1 \
  --test-ratio 0.1 \
  --max-seq-length 2048
```

検証では、存在しない evidence ID の引用、引用なし facts、空の fact/timeline text、時系列逆転、空の uncertainty、単一証拠だけの断定回答、review metadata不足、bundle/evidence hash不一致を reject します。

materialize時はassistant応答を厳密なJSON文字列にします。評価側も同じJSON構造を期待します。

```json
{"schema_version":"git-archaeologist.answer.v1","facts":[],"timeline":[],"inference":"","uncertainty":"","citations":[],"answer":""}
```

`--max-seq-length` は近似token budgetの事前ゲートです。tokenizerによる厳密測定ではありませんが、長すぎるbundleや、citation対象evidenceがSFT入力から欠落する危険を学習前に止めます。

## 4. データ形式を検証する

```powershell
.\scripts\validate_data.ps1 -Path data\samples\react_react_poc.jsonl
```

この検証では、各行が JSON object であること、`messages` があること、`user` と `assistant` が含まれることを確認します。

## 5. データ設定を差し替える

PoC用設定は `configs/data/poc.yaml` です。

```yaml
train_file: data/samples/react_react_poc.jsonl
validation_file:
format: messages
required_roles:
  - user
  - assistant
```

別のデータで試す場合は `train_file` を差し替えるか、実行時に `-TrainFile` を指定します。

## 6. モデル設定を確認する

既定のモデル設定は `configs/model/base.yaml` です。

```yaml
model_name_or_path: Qwen/Qwen3-14B
trust_remote_code: false
torch_dtype: bfloat16
load_in_4bit: true
```

まず `Qwen/Qwen3-14B` でデータ形式、LoRA設定、checkpoint保存、評価の流れを確認します。本命実験では、同じ入口のまま `model_name_or_path` を `Qwen/Qwen2.5-Coder-32B-Instruct` などに切り替えます。

## 7. 学習を実行する

```powershell
.\scripts\train_sft.ps1 -DataConfig configs/data/poc.yaml
```

別ファイルを指定する場合:

```powershell
.\scripts\train_sft.ps1 -DataConfig configs/data/poc.yaml -TrainFile data\samples\your_sample.jsonl
```

Linux の H100 環境で `react/react` の収集、変換、検証、SFT 起動までをまとめて行う場合:

```bash
bash scripts/run_sft_linux.sh --preset react-react-qwen3-14b
```

SFT 本体を起動せず、事前に実行予定コマンドだけ確認する場合:

```bash
bash scripts/run_sft_linux.sh --dry-run --preset react-react-qwen3-14b
```

既に `data/raw/github/react-react/` がある場合は、収集を飛ばして変換と検証から始めます。

```bash
bash scripts/run_sft_linux.sh --skip-collect --preset react-react-qwen3-14b
```

## 7.5 実行前チェック

H100 で SFT を回す前に、GPU を使わずに潰せる問題を先に潰します。

```bash
uv run --system-certs --group dev python -m pytest
uv run --system-certs --group dev python -m llm_tuning_lab.run.sft_pipeline --dry-run --skip-collect --preset react-react-qwen3-14b --include-sync-command
uv run --system-certs --group dev python -m llm_tuning_lab.data.gold_cases validate --bundles data/interim/bundles/react-react.jsonl --gold-cases data/interim/gold_cases/react-react.jsonl
uv run --system-certs --group dev python -m llm_tuning_lab.data.validate data/processed/train.jsonl
uv run --system-certs --group dev python -m llm_tuning_lab.data.validate data/processed/validation.jsonl
uv run --system-certs --group dev python -m llm_tuning_lab.data.validate data/processed/test.jsonl
uv run --system-certs --group dev python -m llm_tuning_lab.train.sft --model-config configs/model/base.yaml --data-config configs/data/react_react_sft.yaml --train-config configs/train/sft.yaml --lora-config configs/train/lora.yaml --train-file data/processed/train.jsonl --validation-file data/processed/validation.jsonl --output-dir outputs/sft/react-react-qwen3-14b --preflight-only
```

確認すること:

- `data/interim/gold_cases/react-react.jsonl` に `review_status: approved` の case がある。
- `data/processed/train.jsonl`、`validation.jsonl`、`test.jsonl` が空ではない。
- 各行が `messages` 形式で、`user` と `assistant` を含む。
- `configs/model/base.yaml` が `Qwen/Qwen3-14B` を指している。
- `configs/train/sft.yaml` が `assistant_only_loss: true` を持っている。
- `outputs/sft/react-react-qwen3-14b` に書き込める。
- `HF_HOME` が十分な容量のあるディスクを指している。

SFT では conversational `messages` をなるべく保持します。`messages` を事前に1本の `text` へ潰すと、assistant の回答だけでなく user や system の文まで学習対象になりやすいためです。このリポジトリでは、根拠や質問を丸暗記させるのではなく、assistant の答え方、根拠の扱い方、不確実性の示し方を学ばせます。

## 7.6 Phase 2: RAFT style データを作る

Phase 2 では、retrieval context に不要な evidence が混ざっていても、関連 evidence を選んで回答する練習をします。入力は引き続き `messages` JSONL ですが、user message には対象 bundle の evidence と、別 bundle から選んだ distractor evidence が入ります。

```powershell
.\scripts\materialize_roadmap_data.ps1 `
  -Mode raft `
  -TrainOutput data\processed\raft_train.jsonl `
  -ValidationOutput data\processed\raft_validation.jsonl

.\scripts\validate_data.ps1 -Path data\processed\raft_train.jsonl
.\scripts\validate_data.ps1 -Path data\processed\raft_validation.jsonl
```

学習は SFT と同じ入口を使います。

```powershell
.\scripts\train_sft.ps1 `
  -DataConfig configs\data\raft.yaml `
  -TrainFile data\processed\raft_train.jsonl `
  -ValidationFile data\processed\raft_validation.jsonl `
  -OutputDir outputs\sft\react-react-raft
```

## 7.7 Phase 3: DPO データを作る

Phase 3 では、同じ prompt に対して「良い Git Archaeologist 回答」と「避けたい回答」の差を学ばせます。DPO JSONL は `prompt`, `chosen`, `rejected` を持ちます。既定では `chosen` は gold case の JSON 回答、`rejected` は引用なし、断定的、uncertainty が空の synthetic bad answer です。gold case に `rejected` または `rejected_answer` がある場合はそれを使えます。

```powershell
.\scripts\materialize_roadmap_data.ps1 `
  -Mode dpo `
  -TrainOutput data\processed\dpo_train.jsonl `
  -ValidationOutput data\processed\dpo_validation.jsonl

.\scripts\validate_data.ps1 -Path data\processed\dpo_train.jsonl -Format dpo
.\scripts\validate_data.ps1 -Path data\processed\dpo_validation.jsonl -Format dpo
```

実行前チェック:

```powershell
.\scripts\train_dpo.ps1 -DataConfig configs\data\dpo.yaml -PreflightOnly
```

DPO を実際に回す場合:

```powershell
.\scripts\train_dpo.ps1 `
  -DataConfig configs\data\dpo.yaml `
  -TrainFile data\processed\dpo_train.jsonl `
  -ValidationFile data\processed\dpo_validation.jsonl `
  -OutputDir outputs\dpo\react-react-qwen3-14b
```

DPO の `rejected` は「学ばせたい悪文」ではなく、`chosen` と比較して下げたい回答です。断定しすぎ、引用がない、retrieval context の不要 evidence に引っ張られる、古い事実を覚えたように話す、uncertainty を消す、といった失敗を入れます。

## 8. 評価する

評価は、固定 benchmark と各方式の予測 JSONL を比較します。推論バックエンド自体はこのリポジトリに固定せず、`evals/results/*_predictions.jsonl` を採点対象にします。

```bash
uv run --system-certs python -m llm_tuning_lab.eval.run_eval \
  --benchmark evals/benchmarks/react-react.jsonl \
  --predictions evals/results/base_rag_predictions.jsonl \
  --output evals/results/base_rag_metrics.json
```

採点では、citation precision / recall、unsupported citation、timeline order、schema validity、不確実性の有無に加えて、fact-level precision / recall、fact citation precision / recall、timeline event precision / recall、answer similarity、inference similarity、unsupported claim count を確認します。

評価はbenchmark全件を基準にします。predictionが欠落したcaseは0点、重複IDと未知IDは `invalid_predictions` としてsummaryに記録します。summaryには `benchmark_count`, `prediction_count`, `matched_count`, `missing_count`, `duplicate_count`, `unknown_count`, `coverage` が含まれます。

CI や実験ゲートでは、strict mode と閾値を使います。

```bash
uv run --system-certs python -m llm_tuning_lab.eval.run_eval \
  --benchmark evals/benchmarks/react-react.jsonl \
  --predictions evals/results/sft_rag_predictions.jsonl \
  --output evals/results/sft_rag_metrics.json \
  --strict \
  --min-coverage 1.0 \
  --min-fact-recall 0.7 \
  --min-answer-similarity 0.5 \
  --min-timeline-event-recall 0.6
```

exit code は、正常評価が0、入力不正が1、predictionファイル欠損が2、coverage閾値未達が3、metric閾値未達が4です。

意味評価は、外部LLM judgeではなく固定benchmarkで再現できる近似指標です。高いスコアは「主要語・イベント・引用の一致が多い」ことを示しますが、完全な意味理解やcitation supportを証明するものではありません。

未知repositoryへの一般化を測る場合は、run presetでrepository holdoutを使います。

```yaml
split_strategy: repository_holdout
validation_repositories:
  - owner/validation-repo
test_repositories:
  - owner/test-repo
```

## 9. 結果を保存する

学習ログや checkpoint は `outputs/`、adapter やモデル成果物は `models/` に置きます。これらは大きくなりやすいため、原則 Git 管理しません。

SFT 実行後は `outputs/sft/.../training_manifest.json` に dataset hash、config hash、git commit、主要依存バージョン、CUDA/GPU情報、split件数を保存します。

## 10. 知見をMemoryに残す

実験中に分かったことは `.memory/fine-tuning/entries/` に残します。

残すべき内容:

- 成功した小さい設定
- データ形式の失敗
- 学習が進まなかった原因
- 評価で見つかった問題
- 初学者が誤解しやすい点
- 次回同じ状況で確認すべきこと

新しいメモを書くときは `.memory/fine-tuning/templates/knowledge-note.md` を使います。
