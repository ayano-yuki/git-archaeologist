# JAICON Fine-tuning 実験報告: 共有H100環境での低VRAM LoRA SFT

作成日: 2026-07-12  
対象: 第1回 JAICON 実環境での Git Archaeologist 向け Fine-tuning 検証

## 1. 概要

本実験では、共有GPUサーバー上で既存の vLLM 推論プロセスを停止せずに、Git Archaeologist 向けの Supervised Fine-tuning を実行できるかを検証した。

Git Archaeologist は、GitHub の Pull Request、Issue、Commit、Review などのリポジトリ履歴を証拠として使い、「なぜその実装になったのか」「どの証拠から何が言えるのか」を説明するローカルLLMを目指すプロジェクトである。

今回のFine-tuningでは、モデルに GitHub 履歴そのものを暗記させるのではなく、以下の回答様式を学習させることを目的とした。

- 証拠を先に見る
- 事実と推論を分ける
- 単一のPRやIssueだけで断定しない
- 不確実性を明示する
- 関連するCommit、Issue、Review、CIログなどとの照合を促す

結論として、`Qwen/Qwen3-8B` を4bit量子化し、LoRA rank 8、最大系列長1024に落とした低VRAM構成により、H100 80GB共有環境で vLLM を停止せずに SFT を完走できた。

## 2. ファインチューニングの構成

### 2.1 実験環境

実験は、さくらのクラウド高火力VRT相当のGPUサーバーで行った。

```text
GPU: NVIDIA H100 80GB HBM3
NVIDIA-SMI: 610.43.02
CUDA UMD: 13.3
OS: Linux 6.8.0-134-generic x86_64
Python: 3.14.6
```

学習成果物の `training_manifest.json` には、実行時環境として以下が記録された。

```json
{
  "cuda_version": "13.0",
  "gpu": "NVIDIA H100 80GB HBM3",
  "platform": "Linux-6.8.0-134-generic-x86_64-with-glibc2.39",
  "python": "3.14.6"
}
```

実験開始時点で、GPU上には3本の vLLM 推論プロセスが動作していた。

```text
VLLM::EngineCore  約16.9GB
VLLM::EngineCore  約16.9GB
VLLM::EngineCore  約17.0GB
合計               約50.8GB
```

H100 80GBのうち約50GBが既に使用されており、空きは約30GBだった。そのため、当初想定していた `Qwen/Qwen3-14B` の学習はOOMリスクが高いと判断した。

### 2.2 採用したモデル

本実験では、低VRAM構成として以下のモデルを採用した。

```text
base model: Qwen/Qwen3-8B
method: 4bit LoRA SFT
```

`Qwen/Qwen3-8B` を選んだ理由は、14BモデルよりVRAM使用量を抑えながら、GitHub履歴の要約や説明に必要な一般的な言語能力を持つためである。

### 2.3 学習方式

学習方式は LoRA を使った SFT である。

SFT は Supervised Fine-tuning の略で、入力と望ましい出力のペアを使ってモデルの応答様式を学習させる手法である。LoRA は、モデル全体の重みを更新するのではなく、小さな追加パラメータだけを学習する省メモリなFine-tuning手法である。

今回生成された成果物は、base model全体ではなく LoRA adapter である。つまり、推論時には `Qwen/Qwen3-8B` に今回生成した adapter を重ねて使う。

### 2.4 モデル設定

使用したモデル設定は以下である。

```yaml
model_name_or_path: Qwen/Qwen3-8B
trust_remote_code: false
torch_dtype: bfloat16
load_in_4bit: true
device_map: auto
```

重要な点は `load_in_4bit: true` である。これにより、base modelを4bit量子化して読み込み、GPUメモリ使用量を抑えた。

### 2.5 SFT設定

学習設定は以下である。

```yaml
seed: 42
output_dir: outputs/sft-lowvram
num_train_epochs: 1
per_device_train_batch_size: 1
gradient_accumulation_steps: 16
learning_rate: 0.0002
warmup_ratio: 0.03
logging_steps: 10
save_steps: 100
bf16: true
max_seq_length: 1024
assistant_only_loss: true
packing: false
gradient_checkpointing: true
eos_token: <|im_end|>
```

`per_device_train_batch_size` は1に抑え、`gradient_accumulation_steps` を16にした。これにより、1回あたりのGPUメモリ使用量を小さくしつつ、実効バッチサイズ16を確保した。

`max_seq_length` は1024にした。系列長を短くすると、長い文脈を扱える範囲は狭くなるが、学習時のメモリ使用量を大きく下げられる。

`assistant_only_loss: true` は、userやsystemの入力文ではなく、assistantの回答部分を主な学習対象にするための設定である。今回の目的は、質問文や証拠文を丸暗記することではなく、証拠を慎重に扱う回答様式を学ばせることなので、この設定を有効にした。

### 2.6 LoRA設定

LoRA設定は以下である。

```yaml
r: 8
lora_alpha: 16
lora_dropout: 0.05
bias: none
task_type: CAUSAL_LM
target_modules:
  - q_proj
  - k_proj
  - v_proj
  - o_proj
  - gate_proj
  - up_proj
  - down_proj
```

LoRA rank `r` は8にした。rankを大きくすると表現力は上がるが、学習対象パラメータとメモリ使用量も増える。今回はvLLMを止めない共有環境での成功を優先し、控えめなrankにした。

## 3. 実験に使用したデータ

### 3.1 データの種類

実験データは、GitHub の `react/react` リポジトリから取得した公開履歴データをもとに生成した。

取得対象には、Pull Request、Issue、Commit、Issue comment、Review comment、Review などが含まれる。

本実験では、GitHub履歴そのものをモデルに暗記させることを目的としていない。raw GitHub recordを、以下のような会話形式のSFTデータへ変換した。

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "Repository, evidence kind, evidence summary ..."},
    {"role": "assistant", "content": "Facts, Inference, Uncertainty ..."}
  ]
}
```

assistant応答は、単一のGitHub recordだけで断定せず、関連証拠と照合するよう促す形式で生成される。

### 3.2 データ生成方法

サーバー上で以下のコマンドを実行し、GitHub raw dataを収集した。

```bash
uv run --system-certs python -m llm_tuning_lab.collect.github \
  --config configs/collect/react_react.yaml \
  --max-pages 2 \
  --per-page 50
```

その後、raw dataをSFT用JSONLに変換した。

```bash
uv run --system-certs python -m llm_tuning_lab.data.prepare \
  --input data/raw/github/react-react \
  --train-output data/processed/train.jsonl \
  --validation-output data/processed/validation.jsonl \
  --validation-ratio 0.2
```

生成結果は以下である。

```text
raw_records: 300
sft_records: 300
train: 240 -> data/processed/train.jsonl
validation: 60 -> data/processed/validation.jsonl
```

### 3.3 データ検証

生成したJSONLは、学習前に検証した。

```bash
uv run --system-certs python -m llm_tuning_lab.data.validate data/processed/train.jsonl
uv run --system-certs python -m llm_tuning_lab.data.validate data/processed/validation.jsonl
```

結果は以下である。

```text
OK: data/processed/train.jsonl
OK: data/processed/validation.jsonl
```

この時点で、学習に必要な `train.jsonl` と `validation.jsonl` が存在し、形式チェックを通過した。

### 3.4 データ上の制約

GitHub API収集は、認証なしのrate limitにより途中で停止した。そのため、今回のデータは `react/react` の履歴全体ではなく、途中まで取得できた300件のraw recordに基づく小規模データである。

また、今回はtest splitを生成していない。

```text
train: 240
validation: 60
test: none
```

したがって、本実験の結果は「Fine-tuningパイプラインが実環境で完走できた」ことを示すものであり、「モデル品質が十分に向上した」ことを厳密に示すものではない。

## 4. 実験の流れ

この章では、最終的に成功した本実験の流れを記載する。途中で発生した失敗や動作検証はAppendixに分けて記載する。

### 4.1 環境変数の設定

Hugging Face cacheは、ユーザーのホームディレクトリ配下を使った。

```bash
export HF_HOME="$HOME/hf_cache"
export HF_TOKEN_PATH="$HOME/.huggingface/token"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export PATH="$HOME/.local/bin:$PATH"
```

`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` は、CUDAメモリ断片化による失敗を減らすために設定した。

### 4.2 データ生成

GitHub raw dataを収集し、SFT JSONLへ変換した。

```bash
uv run --system-certs python -m llm_tuning_lab.collect.github \
  --config configs/collect/react_react.yaml \
  --max-pages 2 \
  --per-page 50

uv run --system-certs python -m llm_tuning_lab.data.prepare \
  --input data/raw/github/react-react \
  --train-output data/processed/train.jsonl \
  --validation-output data/processed/validation.jsonl \
  --validation-ratio 0.2
```

### 4.3 データ検証

```bash
uv run --system-certs python -m llm_tuning_lab.data.validate data/processed/train.jsonl
uv run --system-certs python -m llm_tuning_lab.data.validate data/processed/validation.jsonl
```

検証結果:

```text
OK: data/processed/train.jsonl
OK: data/processed/validation.jsonl
```

### 4.4 Fine-tuning実行

```bash
uv run --system-certs python -m llm_tuning_lab.train.sft \
  --model-config configs/model/qwen3_8b_lowvram.yaml \
  --data-config configs/data/sft.yaml \
  --train-config configs/train/sft_lowvram.yaml \
  --lora-config configs/train/lora_lowvram.yaml \
  --output-dir outputs/sft/react-react-qwen3-8b-lowvram
```

このコマンドにより、`Qwen/Qwen3-8B` に対する4bit LoRA SFTを1 epoch実行した。

### 4.5 成果物確認

学習後、以下で成果物を確認した。

```bash
ls -lah outputs/sft/react-react-qwen3-8b-lowvram
cat outputs/sft/react-react-qwen3-8b-lowvram/training_manifest.json
```

成果物は以下である。

```text
adapter_config.json
adapter_model.safetensors
chat_template.jinja
checkpoint-15
README.md
tokenizer_config.json
tokenizer.json
training_args.bin
training_manifest.json
```

`adapter_model.safetensors` と `adapter_config.json` が存在するため、LoRA adapterとして学習成果物が保存されたと言える。

## 5. 実験結果

### 5.1 学習結果

本実験の最終的な学習ログは以下である。

```text
train examples: 240
validation examples: 60
train_runtime: 120.2
train_samples_per_second: 1.996
train_steps_per_second: 0.125
train_loss: 0.8628
mean_token_accuracy: 0.8757
epoch: 1
steps: 15/15
```

### 5.2 training_manifest

`training_manifest.json` には以下の情報が記録された。

```json
{
  "base_model": "Qwen/Qwen3-8B",
  "effective_batch_size": 16,
  "git_commit": "03fb5ae35118a6a7a3f16e6b16988b5462944e97",
  "seed": 42,
  "splits": {
    "test": null,
    "train": 240,
    "validation": 60
  },
  "versions": {
    "bitsandbytes": "0.49.2",
    "datasets": "5.0.0",
    "peft": "0.19.1",
    "torch": "2.13.0",
    "transformers": "5.13.0",
    "trl": "1.8.0"
  }
}
```

### 5.3 成功判定

本実験で「Fine-tuningできた」と判断した根拠は以下である。

- SFT用データ `train.jsonl` と `validation.jsonl` を生成できた
- 生成データがvalidatorを通過した
- `Qwen/Qwen3-8B` を4bit量子化でロードできた
- LoRA設定を適用して学習が完走した
- `adapter_model.safetensors` が生成された
- `training_manifest.json` が生成された
- PEFT adapterとして読み込み、推論テストができた

特に重要なのは、以下の3ファイルである。

```text
outputs/sft/react-react-qwen3-8b-lowvram/adapter_model.safetensors
outputs/sft/react-react-qwen3-8b-lowvram/adapter_config.json
outputs/sft/react-react-qwen3-8b-lowvram/training_manifest.json
```

これらにより、学習済みLoRA adapterが実際に保存されたことを確認できる。

### 5.4 推論テスト結果

学習済みadapterをbase modelに重ねて推論したところ、架空のPull Request evidenceに対して、以下のような回答が得られた。

```text
The evidence should be used as one piece of a larger reconstruction, not as a standalone source. The pull request record shows the PR title, author, and a summary of the change, but it does not include the full diff, commit history, or context from related issues or discussions. Therefore, the reconstruction should:

1. Use the pull request as a starting point to identify the scope of the change, but not as the final answer.
2. Cross-reference with other evidence such as commit history, issue discussions, and code diffs to build a more complete picture.
3. Acknowledge limitations of the pull request record, such as the lack of full diff or detailed reasoning, and avoid overgeneralizing conclusions from it.

In short, the pull request is a useful but incomplete source for reconstructing repository history.
```

この出力は、単一証拠から断定せず、他の証拠との照合を促し、不完全性を述べている。したがって、今回学習させたい回答方針と概ね一致している。

ただし、厳密な性能評価は未実施である。今回の推論テストは、adapterが読み込めることと、期待する方向の回答が出ることを確認するためのスモークテストである。

## 6. 結論

vLLMが約50GBのVRAMを使用している共有H100環境でも、低VRAM構成に落とすことでGit Archaeologist向けのSFTを完走できた。

最終構成は以下である。

```text
base model: Qwen/Qwen3-8B
method: 4bit LoRA SFT
LoRA rank: 8
max_seq_length: 1024
effective batch size: 16
train examples: 240
validation examples: 60
train loss: 0.8628
mean token accuracy: 0.8757
output: outputs/sft/react-react-qwen3-8b-lowvram
commit: 03fb5ae Add low-VRAM SFT preset
```

本実験により、JAICONの共有GPU運用でも、モデルサイズと学習設定を調整すればFine-tuning実験を実施できることが分かった。

一方で、今回のデータは小規模であり、test splitやRAG込みの比較評価はまだ行っていない。そのため、次の段階では `GITHUB_TOKEN` を設定してより安定してデータを収集し、base model、RAG-only、SFT、SFT+RAGの比較評価を行う必要がある。

## Appendix A. 動作検証実験

### A.1 PoCデータによるpreflight

最初に、コミット済みの小さなPoCデータで設定とデータの存在を確認した。

```bash
uv run --system-certs python -m llm_tuning_lab.train.sft \
  --model-config configs/model/qwen3_8b_lowvram.yaml \
  --data-config configs/data/poc.yaml \
  --train-config configs/train/sft_lowvram.yaml \
  --lora-config configs/train/lora_lowvram.yaml \
  --output-dir outputs/sft/react-react-qwen3-8b-lowvram-poc \
  --preflight-only
```

結果:

```text
OK: SFT configs and data files are ready.
```

### A.2 PoCデータによる学習

```bash
uv run --system-certs python -m llm_tuning_lab.train.sft \
  --model-config configs/model/qwen3_8b_lowvram.yaml \
  --data-config configs/data/poc.yaml \
  --train-config configs/train/sft_lowvram.yaml \
  --lora-config configs/train/lora_lowvram.yaml \
  --output-dir outputs/sft/react-react-qwen3-8b-lowvram-poc
```

結果:

```text
train_runtime: 5.955
train_loss: 3.998
mean_token_accuracy: 0.6698
epoch: 1
```

PoC実験により、モデルロード、tokenize、LoRA学習、adapter保存が実環境で可能であることを確認した。

### A.3 推論スモークテスト

学習済みadapterを読み込んで、架空のPR evidenceに対して推論した。このテストの目的は、品質評価ではなく、以下を確認することである。

- base model `Qwen/Qwen3-8B` を読み込めること
- `outputs/sft/react-react-qwen3-8b-lowvram` のLoRA adapterをPEFTで重ねられること
- adapter適用後のモデルが実際にテキストを生成できること
- 出力が「単一証拠から断定しない」という学習方針に概ね沿うこと

投げたプロンプトは、学習データの形式に近い架空のPull Request evidenceである。

```text
Repository: react/react
Evidence kind: pull
Evidence id: #12345
Evidence summary:
- Title: Fix hydration mismatch caused by async rendering
- State: closed
- Author: example-user
- Body excerpt: This PR adjusts hydration behavior after reports that async rendering could produce mismatched markup during client startup. The change adds a guard and updates tests for the affected path.

Explain how this evidence should be used when reconstructing repository history.

/no_think
```

`/no_think` は、Qwen3が通常出すことのある `<think>` 形式の思考出力を抑制し、最終回答だけを確認しやすくするために入れた。提出資料に載せる回答や通常の評価では、内部思考ではなく最終回答を比較対象にするためである。

推論テストでは、以下のスクリプトを `/tmp/test_adapter_no_think.py` として作成して実行した。

```python
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

base = "Qwen/Qwen3-8B"
adapter = "outputs/sft/react-react-qwen3-8b-lowvram"

prompt = """Repository: react/react
Evidence kind: pull
Evidence id: #12345
Evidence summary:
- Title: Fix hydration mismatch caused by async rendering
- State: closed
- Author: example-user
- Body excerpt: This PR adjusts hydration behavior after reports that async rendering could produce mismatched markup during client startup. The change adds a guard and updates tests for the affected path.

Explain how this evidence should be used when reconstructing repository history.

/no_think"""

tokenizer = AutoTokenizer.from_pretrained(adapter)
quant = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_quant_type="nf4",
)
model = AutoModelForCausalLM.from_pretrained(
    base,
    quantization_config=quant,
    device_map="auto",
    dtype=torch.bfloat16,
)
model = PeftModel.from_pretrained(model, adapter)
model.eval()

messages = [
    {
        "role": "system",
        "content": "You are Git Archaeologist. Use repository evidence first, separate facts from inference, and avoid claiming that a single record proves more than it shows.",
    },
    {"role": "user", "content": prompt},
]

text = tokenizer.apply_chat_template(
    messages,
    add_generation_prompt=True,
    tokenize=False,
    enable_thinking=False,
)
inputs = tokenizer(text, return_tensors="pt")
device = next(model.parameters()).device
inputs = {key: value.to(device) for key, value in inputs.items()}

with torch.no_grad():
    output = model.generate(
        **inputs,
        max_new_tokens=220,
        do_sample=False,
        pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
    )

generated = output[0][inputs["input_ids"].shape[-1]:]
print(tokenizer.decode(generated, skip_special_tokens=True))
```

実行コマンドは以下である。

```bash
export HF_HOME="$HOME/hf_cache"
export PATH="$HOME/.local/bin:$PATH"
uv run --system-certs python /tmp/test_adapter_no_think.py
```

このスクリプトでは、base modelを4bitで読み込み、その上にLoRA adapterを重ねている。`tokenizer.apply_chat_template` でsystem/user messagesをQwen3のチャット形式に変換し、`model.generate` で最終回答を生成した。

## Appendix B. 失敗と対処

### B.1 `uv: command not found`

実環境には最初 `uv` が入っていなかった。

対処:

```bash
python3 -m pip install --user uv
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

### B.2 Hugging Face共有キャッシュの権限エラー

最初は `HF_HOME=/opt/jaicon_shared/hf_cache` を使ったが、ユーザーに書き込み権限がなく、モデルダウンロードに失敗した。

エラー概要:

```text
PermissionError: Permission denied: /opt/jaicon_shared/hf_cache/hub/models--Qwen--Qwen3-8B
```

対処:

```bash
mkdir -p "$HOME/hf_cache"
export HF_HOME="$HOME/hf_cache"
```

### B.3 `data/processed/train.jsonl` が存在しない

`data/processed/` はGit管理外であり、実環境には `train.jsonl` と `validation.jsonl` が存在しなかった。

エラー概要:

```text
FileNotFoundError: train_file does not exist: data/processed/train.jsonl
```

対処として、実環境でGitHub raw dataからSFTデータを生成した。

### B.4 GitHub API rate limit

GitHub raw data収集中に、認証なしAPIのrate limitに到達した。

エラー概要:

```text
HTTP Error 403: rate limit exceeded
```

今回は途中まで取得できた300件のraw recordから学習データを生成して実験を継続した。次回以降は以下を設定する。

```bash
export GITHUB_TOKEN=...
```

### B.5 Qwen3のthinking出力

推論テスト時、Qwen3が `<think>` から始まる思考出力を返した。これは学習失敗ではなく、Qwen3の通常挙動である。

対処として、プロンプトに `/no_think` を追加し、可能な場合はchat templateの `enable_thinking=False` を使う。

## Appendix C. 成果物の保全

学習成果物はGit管理外の `outputs/` に保存される。提出や保管のため、以下でアーカイブした。

```bash
tar -czf outputs/sft/react-react-qwen3-8b-lowvram.tar.gz \
  -C outputs/sft react-react-qwen3-8b-lowvram
```
