# Fine-tuning Types

## 目的

このメモは、LLM のファインチューニング手法を「何を学ばせるか」「どんなデータが必要か」「Git Archaeologist で使うべきか」で分類するための整理です。

このリポジトリの基本方針は、**知識は RAG、推論様式は Fine-tuning** です。GitHub 履歴の事実そのものをモデルに覚えさせるのではなく、根拠の扱い方、事実と推論の分離、不確実性の表現、レビュー思考を学ばせます。

## 全体像

```text
Fine-tuning
  1. 追加学習系
     - Continued Pretraining
     - Domain-Adaptive Pretraining
  2. 教師あり学習系
     - SFT
     - Instruction Tuning
     - Tool / Function Calling SFT
     - RAG-oriented SFT / RAFT
  3. 効率化系
     - Full Fine-tuning
     - LoRA
     - QLoRA
     - LoRA variants
  4. 嗜好最適化系
     - Reward Modeling + RLHF
     - DPO
     - IPO / KTO / ORPO / SimPO
  5. 推論能力強化系
     - Reasoning SFT
     - Rejection Sampling Fine-tuning
     - RL with verifiable rewards
     - GRPO
  6. 蒸留系
     - Knowledge Distillation
     - Self-distillation
     - Reasoning Distillation
```

## 1. 追加学習系

### Continued Pretraining

既存の基盤モデルに対して、通常の next-token prediction で追加学習する方法です。目的は「答え方」ではなく、特定ドメインの文章分布に慣らすことです。

向いているケース:

- 医療、法律、金融、コードなど、用語や文体が一般コーパスと大きく違う。
- 大量で品質の揃ったドメインテキストがある。
- モデルにドメインの言語感覚を持たせたい。

注意点:

- 事実をモデルに焼き込む方向に寄りやすい。
- データが古くなると、古い知識を出し続ける危険がある。
- GitHub 履歴のように更新される事実は RAG に置く方が安全。

Git Archaeologist での位置づけ:

- 優先度は低い。
- GitHub 履歴を丸ごと continued pretraining するのは避ける。
- 大量の一般的なコードレビュー文体や設計議論文体を学ばせる場合だけ検討する。

### Domain-Adaptive Pretraining

Continued Pretraining のうち、特定ドメインへ寄せる目的が明確なものです。数学、コード、医学などで使われます。

近年の例として、DeepSeekMath は数学関連データで追加事前学習したうえで、SFT や RL を組み合わせています。

## 2. 教師あり学習系

### SFT

SFT は Supervised Fine-Tuning の略です。ファインチューニングの一種で、入力と理想出力のペアを使ってモデルの振る舞いを学ばせます。

代表的な形式:

```json
{"messages":[{"role":"user","content":"このPRの設計判断を説明して"},{"role":"assistant","content":"根拠はPR本文と関連Issueです。事実として... 推論として..."}]}
```

向いているケース:

- 回答スタイルを揃えたい。
- 根拠の使い方を学ばせたい。
- 初手のモデルに「こう答えてほしい」という型を入れたい。

Git Archaeologist での位置づけ:

- 最初に取り組む中心手法。
- `assistant_only_loss: true` を使い、user/system ではなく assistant 応答を主に学習対象にする。
- 事実の暗記ではなく、根拠引用、慎重な推論、リスク分析、レビュー観点を学ばせる。

### Instruction Tuning

SFT の一種として扱われることが多い手法です。「要約して」「比較して」「JSONで返して」「リスクを列挙して」のような指示に従う能力を強めます。

向いているケース:

- 汎用的な指示追従を強めたい。
- 出力形式や粒度を安定させたい。
- 基盤モデルがプロジェクト固有のタスク指示に弱い。

注意点:

- 指示が雑なデータを入れると、モデルの出力も雑になる。
- 形式だけを学んで、根拠の質が上がらないことがある。

### Tool / Function Calling SFT

ツール呼び出し、関数呼び出し、JSON schema などを学ばせる SFT です。

向いているケース:

- GitHub API、検索、RAG、評価ツールなどを使い分ける agent を作りたい。
- いつツールを呼ぶべきか、いつ自然言語で答えるべきかを学ばせたい。

Git Archaeologist での位置づけ:

- RAG や GitHub evidence 検索と組み合わせる段階で検討する。
- まずは通常の SFT で根拠を扱う答え方を安定させる。

### RAG-oriented SFT / RAFT

RAG の検索結果を前提に、関連文書を使って答える訓練です。RAFT は、質問と取得文書を与え、不要な文書を無視し、必要な文書を根拠として使う能力を学ばせる post-training recipe です。

向いているケース:

- RAG があるが、モデルが検索結果をうまく使えない。
- 無関係な検索結果に引っ張られる。
- 回答に根拠を明示させたい。

Git Archaeologist での位置づけ:

- かなり相性が良い。
- 将来的には、Issue、PR、Commit、Review、CI log を retrieval context として与え、正しい evidence を選んで説明するデータを作る。

## 3. 効率化系

### Full Fine-tuning

モデルの全パラメータを更新する方法です。

利点:

- 表現力が高い。
- 大きなドメイン適応では強いことがある。

欠点:

- VRAM、時間、保存容量が大きい。
- 実験比較が重い。
- 失敗時のコストが高い。

Git Archaeologist での位置づけ:

- H100 1枚でも、まずは避ける。
- 初期実験は LoRA / QLoRA で十分。

### LoRA

LoRA は Low-Rank Adaptation の略です。元モデルの重みを凍結し、小さな低ランク行列だけを学習します。元論文では、巨大モデルの downstream adaptation で学習パラメータとGPUメモリを大きく削減できることが示されました。

向いているケース:

- まず小さく実験したい。
- adapter を切り替えて複数実験を比較したい。
- 元モデルを壊さずにタスク適応したい。

Git Archaeologist での位置づけ:

- 標準手法。
- 実験ごとに adapter を保存して比較する。

### QLoRA

QLoRA は、4bit 量子化した基盤モデルに LoRA adapter を載せて学習する方法です。QLoRA 論文では、4bit quantized pretrained model に LoRA で勾配を流すことで、大きなモデルを少ないメモリで fine-tuning できることが示されました。

向いているケース:

- 14B、32B、65B 級を限られたGPUで触りたい。
- Full fine-tuning は重すぎるが、モデルサイズは落としたくない。

Git Archaeologist での位置づけ:

- 現在の第一候補。
- `Qwen/Qwen3-14B` + QLoRA + SFT から始める。

### LoRA variants

近年は LoRA の改良手法も増えています。

- LoRA+: LoRA の2つの adapter matrix に異なる learning rate を使うことで、効率や速度改善を狙う。
- rank allocation 系: layer ごとに rank を変え、限られた adapter 予算を重要な場所に寄せる。
- quantized LoRA 改良: 量子化誤差と低ランク更新を同時に扱う。

Git Archaeologist での位置づけ:

- 最初から使わない。
- 通常の QLoRA でボトルネックが見えたら検討する。

## 4. 嗜好最適化系

### Reward Modeling + RLHF

人間の好みを reward model に学ばせ、その reward を最大化するようにモデルを強化学習で更新する方法です。InstructGPT の代表的な流れは、SFT、reward model、RLHF です。

向いているケース:

- 人間評価を大量に集められる。
- 安全性、親切さ、指示追従などの総合的な好みを最適化したい。

注意点:

- 実装と運用が重い。
- reward hacking が起きることがある。
- 最初の実験には向かない。

### DPO

DPO は Direct Preference Optimization の略です。`chosen` と `rejected` のペアを使い、reward model やRLループを明示的に作らずに preference alignment を行います。

向いているケース:

- 良い回答と悪い回答のペアを作れる。
- SFT 後に「より良い回答」を選ばせたい。
- RLHF より軽い preference optimization から始めたい。

Git Archaeologist での例:

```text
prompt: このPRのリスクを説明して
chosen: 根拠を分け、不確実性も書く回答
rejected: 断定が多く、Issue本文だけを根拠にする回答
```

### IPO / KTO / ORPO / SimPO

DPO 以降、より軽い、またはデータ要件の違う preference optimization が増えています。

- IPO: preference 学習の理論的な整理から生まれた直接最適化系。
- KTO: pairwise preference ではなく、desirable / undesirable のような二値フィードバックを活かしやすい。
- ORPO: SFT と preference alignment を一体化し、reference model なしで odds ratio を使う。
- SimPO: sequence の平均 log probability を reward として使い、reference model なしで効率化する。

Git Archaeologist での位置づけ:

- SFT の次に DPO を優先。
- ペア比較データが作りにくく、良い/悪いの二値ラベルが中心なら KTO を検討する。
- 実験コストや reference model の重さが問題になったら ORPO / SimPO を調べる。

## 5. 推論能力強化系

### Reasoning SFT

解答だけでなく、途中の考え方、検証、反省、根拠整理のプロセスを含むデータで SFT する方法です。

向いているケース:

- 数学、コード、設計判断、障害分析など、結論までの筋道が重要。
- 回答の透明性を上げたい。

注意点:

- chain-of-thought をそのまま公開・保存すべきかは別問題。
- 実運用では、内部推論を長く出させるより、根拠、判断、限界を簡潔に説明させる設計が扱いやすい。

Git Archaeologist での位置づけ:

- 「内部思考の全文」ではなく、観察可能な説明プロセスを学ばせる。
- `Facts`, `Inference`, `Uncertainty`, `Next checks` のような構造が有効。

### Rejection Sampling Fine-tuning

モデルに複数回答を生成させ、正解や評価器で良いものだけを選んで SFT データにする方法です。

向いているケース:

- 自動採点できるタスクがある。
- 回答候補を大量生成できる。
- 人間が全件を書くのは難しい。

Git Archaeologist での位置づけ:

- すぐには難しい。
- 将来、テスト可能な「原因推定」「修正案」「レビュー指摘」などを評価できるようになったら検討する。

### RL with verifiable rewards / GRPO

正解判定やテスト結果など、検証可能な reward を使って強化学習する方法です。DeepSeekMath は GRPO を導入し、DeepSeek-R1 では大規模RLによる推論能力強化が注目されました。

向いているケース:

- 数学の正答、コードのテスト通過、形式チェックなど reward を自動化できる。
- SFT だけでは推論能力が伸びにくい。

注意点:

- reward が雑だと、モデルは reward の穴を突く。
- Git Archaeologist の「設計理由の説明」は自動正解判定が難しい。

Git Archaeologist での位置づけ:

- 当面は優先度低。
- CI結果やテスト通過のように検証可能な部分だけ、将来の研究対象にする。

## 6. 蒸留系

### Knowledge Distillation

大きな teacher model の出力を使って、小さな student model を学習する方法です。

向いているケース:

- 高性能モデルの回答様式を小さいモデルに移したい。
- 実行コストを下げたい。
- synthetic data を作れる。

注意点:

- teacher の癖や誤りも移る。
- teacher の利用規約やデータ利用条件に注意する。

### Reasoning Distillation

推論に強い teacher model から、理由づけや解法パターンを蒸留する方法です。DeepSeek-R1 では、R1 由来の reasoning data を使った distill model も公開され、推論能力の移植が大きな流れになりました。

Git Archaeologist での位置づけ:

- 将来候補。
- まずは自分たちの評価軸で、teacher 出力が本当に良いかを検証する。

## データ形式で見る分類

| 種類 | データ形式 | 代表用途 | このリポジトリでの優先度 |
| --- | --- | --- | --- |
| SFT | prompt/response, messages | 答え方を学ばせる | 高 |
| Instruction Tuning | instruction/response | 指示追従 | 中 |
| RAG-oriented SFT | question + retrieved docs + answer | RAG文脈の使い方 | 高 |
| DPO | prompt + chosen + rejected | 良い回答を選ぶ | 中 |
| KTO | prompt + desirable/undesirable | 二値評価の活用 | 中 |
| ORPO / SimPO | preference data | 軽量な嗜好最適化 | 低から中 |
| Continued Pretraining | raw text | ドメイン文体への適応 | 低 |
| RLHF / GRPO | reward付きrollout | 高度な最適化 | 低 |
| Distillation | teacher output | 小型化、様式移植 | 中 |

## Git Archaeologist での推奨ロードマップ

### Phase 1: SFT + QLoRA

目的:

- 根拠を先に出す。
- 事実と推論を分ける。
- 不確実性を明示する。
- レビューや障害分析の観点を揃える。

使うデータ:

- `messages` JSONL
- assistant-only loss
- GitHub evidence をそのまま暗記させない説明データ

運用:

```powershell
.\scripts\validate_data.ps1 -Path data\samples\react_react_poc.jsonl
.\scripts\train_sft.ps1 -DataConfig configs\data\poc.yaml
```

### Phase 2: RAG-oriented SFT / RAFT style

目的:

- retrieval context から関連 evidence を選ぶ。
- 不要な evidence に引っ張られない。
- 回答に根拠を含める。

使うデータ:

- question
- retrieved Issue / PR / Commit / Review
- answer with citations
- distractor evidence

運用:

```powershell
.\scripts\materialize_roadmap_data.ps1 `
  -Mode raft `
  -TrainOutput data\processed\raft_train.jsonl `
  -ValidationOutput data\processed\raft_validation.jsonl

.\scripts\validate_data.ps1 -Path data\processed\raft_train.jsonl
.\scripts\train_sft.ps1 `
  -DataConfig configs\data\raft.yaml `
  -TrainFile data\processed\raft_train.jsonl `
  -ValidationFile data\processed\raft_validation.jsonl `
  -OutputDir outputs\sft\react-react-raft
```

### Phase 3: DPO

目的:

- 「良いGit Archaeologist回答」と「悪い回答」の差を学ばせる。
- 断定しすぎる回答、根拠が薄い回答、古い事実を覚えたように話す回答を避ける。

使うデータ:

- prompt
- chosen
- rejected

運用:

```powershell
.\scripts\materialize_roadmap_data.ps1 `
  -Mode dpo `
  -TrainOutput data\processed\dpo_train.jsonl `
  -ValidationOutput data\processed\dpo_validation.jsonl

.\scripts\validate_data.ps1 -Path data\processed\dpo_train.jsonl -Format dpo
.\scripts\validate_data.ps1 -Path data\processed\dpo_validation.jsonl -Format dpo
.\scripts\train_dpo.ps1 -DataConfig configs\data\dpo.yaml -PreflightOnly
.\scripts\train_dpo.ps1 `
  -DataConfig configs\data\dpo.yaml `
  -TrainFile data\processed\dpo_train.jsonl `
  -ValidationFile data\processed\dpo_validation.jsonl `
  -OutputDir outputs\dpo\react-react-qwen3-14b
```

### Phase 4: 評価と必要に応じた拡張

比較するもの:

- base model
- RAG-only
- SFT
- RAG + SFT
- RAG + SFT + DPO

必要が見えてから検討するもの:

- KTO
- ORPO / SimPO
- reasoning distillation
- verifiable reward RL

## よくある誤解

### SFT はファインチューニングのことか

SFT はファインチューニングの一種です。すべてのファインチューニングが SFT ではありません。

### LoRA と SFT は同じ分類か

違います。SFT は「何を学ばせるか」という学習目的・データ形式の分類です。LoRA は「どのパラメータを更新するか」という効率化の分類です。

つまり、`SFT + LoRA` や `DPO + LoRA` のように組み合わせます。

### QLoRA は学習目的か

違います。QLoRA は量子化モデルに LoRA を載せて省メモリに学習する方法です。目的は SFT でも DPO でもあり得ます。

### RAG と Fine-tuning は競合するか

競合しません。RAG は事実を取り出す仕組み、Fine-tuning は取り出した事実をどう扱うかを学ばせる仕組みです。

このリポジトリでは、GitHub履歴の事実は RAG、推論様式は Fine-tuning に寄せます。

## 研究メモ

- LoRA: 低ランク adapter だけを学習し、巨大モデルの downstream adaptation を軽くする。
- QLoRA: 4bit 量子化と LoRA により、大きなモデルの fine-tuning を現実的にする。
- InstructGPT / RLHF: SFT と人間フィードバックを組み合わせ、指示追従とアラインメントを改善する。
- DPO: reward model と明示的RLを使わず、preference pair から直接最適化する。
- KTO: pairwise preference ではなく、desirable / undesirable の二値信号を使いやすくする。
- ORPO / SimPO: reference model を使わない、または軽量化した preference optimization の流れ。
- RAFT: RAG環境で、関連文書を使い、不要文書を無視する能力を fine-tuning する。
- GRPO / DeepSeek-R1: verifiable reward や group relative advantage を使った推論能力強化の流れ。

## 参考文献

- LoRA: Low-Rank Adaptation of Large Language Models: https://arxiv.org/abs/2106.09685
- QLoRA: Efficient Finetuning of Quantized LLMs: https://arxiv.org/abs/2305.14314
- Training language models to follow instructions with human feedback: https://arxiv.org/abs/2203.02155
- Direct Preference Optimization: Your Language Model is Secretly a Reward Model: https://arxiv.org/abs/2305.18290
- KTO: Model Alignment as Prospect Theoretic Optimization: https://arxiv.org/abs/2402.01306
- ORPO: Monolithic Preference Optimization without Reference Model: https://arxiv.org/abs/2403.07691
- SimPO: Simple Preference Optimization with a Reference-Free Reward: https://arxiv.org/abs/2405.14734
- RAFT: Adapting Language Model to Domain Specific RAG: https://arxiv.org/abs/2403.10131
- DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models: https://arxiv.org/abs/2402.03300
- DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning: https://arxiv.org/abs/2501.12948
- TRL SFTTrainer docs: https://huggingface.co/docs/trl/main/en/sft_trainer
