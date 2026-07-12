# Low-VRAM SFT on a Shared H100 With vLLM Running

## Summary

On 2026-07-12, a low-VRAM Qwen3-8B 4bit LoRA SFT run completed on a shared H100 80GB server while three vLLM processes were still using about 50GB of VRAM. The original Qwen3-14B plan was risky under that memory pressure, so the experiment used `Qwen/Qwen3-8B`, 4bit loading, LoRA rank 8, `max_seq_length: 1024`, and gradient accumulation 16.

The run produced a PEFT LoRA adapter, a checkpoint, and a `training_manifest.json`. This proves the SFT pipeline can run in the shared JAICON-style environment, but it does not prove final model quality because the dataset was small and no held-out test evaluation was performed.

## Context

The target environment was a Sakura Cloud high-power VRT-style server with one NVIDIA H100 80GB HBM3 GPU. The team wanted to fine-tune without stopping existing vLLM services. At the start of the session, `nvidia-smi` showed three `VLLM::EngineCore` processes using about 16.9GB each, for roughly 50.8GB of GPU memory already allocated.

The repository default SFT model was `Qwen/Qwen3-14B`, but that model was too risky with only about 30GB free VRAM. A low-VRAM path was added in commit `03fb5ae Add low-VRAM SFT preset`.

Relevant configuration files:

- `configs/model/qwen3_8b_lowvram.yaml`
- `configs/train/sft_lowvram.yaml`
- `configs/train/lora_lowvram.yaml`
- `configs/run/react_react_qwen3_8b_lowvram.yaml`

## What Happened

First, `uv` was not installed on the server. It was installed with:

```bash
python3 -m pip install --user uv
export PATH="$HOME/.local/bin:$PATH"
```

Second, the shared Hugging Face cache at `/opt/jaicon_shared/hf_cache` was not writable by the user. Downloading `Qwen/Qwen3-8B` failed with a permission error. The workaround was to use a user-owned cache:

```bash
mkdir -p "$HOME/hf_cache"
export HF_HOME="$HOME/hf_cache"
export HF_TOKEN_PATH="$HOME/.huggingface/token"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

Third, a tiny committed PoC dataset was used to verify that the low-VRAM training path could load the model, tokenize data, train, and save an adapter. That run completed and produced `outputs/sft/react-react-qwen3-8b-lowvram-poc/adapter_model.safetensors`.

Fourth, the full local `data/processed/train.jsonl` and `validation.jsonl` were missing on the server because `data/processed/` is Git-ignored. The server generated data from GitHub raw records:

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

GitHub collection hit unauthenticated API rate limits, but partial raw records were enough for the PoC SFT dataset:

```text
raw_records: 300
sft_records: 300
train: 240 -> data/processed/train.jsonl
validation: 60 -> data/processed/validation.jsonl
```

Both generated files passed validation:

```text
OK: data/processed/train.jsonl
OK: data/processed/validation.jsonl
```

The final low-VRAM SFT command completed:

```bash
uv run --system-certs python -m llm_tuning_lab.train.sft \
  --model-config configs/model/qwen3_8b_lowvram.yaml \
  --data-config configs/data/sft.yaml \
  --train-config configs/train/sft_lowvram.yaml \
  --lora-config configs/train/lora_lowvram.yaml \
  --output-dir outputs/sft/react-react-qwen3-8b-lowvram
```

Observed training result:

```text
train examples: 240
validation examples: 60
train_runtime: 120.2 seconds
train_loss: 0.8628
mean_token_accuracy: 0.8757
epoch: 1
steps: 15/15
```

The output directory contained the expected adapter artifacts:

```text
adapter_config.json
adapter_model.safetensors
checkpoint-15
training_manifest.json
```

The manifest recorded:

```text
base_model: Qwen/Qwen3-8B
effective_batch_size: 16
gpu: NVIDIA H100 80GB HBM3
python: 3.14.6
torch: 2.13.0
transformers: 5.13.0
trl: 1.8.0
```

A manual inference smoke test loaded the base model plus adapter through PEFT and generated a cautious repository-history answer. Qwen3 initially emitted `<think>` text; adding `/no_think` and disabling thinking in the chat template suppressed that output.

## Beginner Explanation

Fine-tuning here means supervised fine-tuning, or SFT. The model sees examples of user messages and desired assistant responses. In this repository, the goal is not to make the model memorize GitHub history. The goal is to teach a style of reasoning: use evidence first, separate facts from inference, and explain uncertainty.

LoRA is a memory-efficient fine-tuning method. Instead of changing all base model weights, it trains small adapter matrices. The base model remains `Qwen/Qwen3-8B`, and the learned result is a separate adapter file such as `adapter_model.safetensors`.

4bit loading reduces GPU memory by loading the base model in quantized form. This is why the experiment could run while vLLM was already using much of the H100. However, 4bit LoRA still needs memory for activations, optimizer state, CUDA workspace, and temporary allocations. Reducing the model from 14B to 8B and reducing `max_seq_length` from 2048 to 1024 made the run much safer.

`data/processed/` is intentionally not committed because processed datasets may be large or sensitive. That means a new server will not automatically have `train.jsonl` and `validation.jsonl`; they must be generated or copied before training.

## Why It Matters

Shared event servers often run inference services and training experiments at the same time. If every experiment assumes exclusive GPU access, the team loses time coordinating shutdowns. This run shows a practical compromise: keep vLLM alive, but lower the training configuration enough to complete a LoRA SFT experiment.

The run also exposed four common real-environment blockers that are easy to miss locally:

- The command runner `uv` may not be installed.
- Shared Hugging Face cache permissions may be wrong.
- Git-ignored processed data will be missing on the server.
- GitHub collection may hit rate limits without `GITHUB_TOKEN`.

Ignoring these issues can make a good training configuration look broken. Handling them separately makes debugging much cleaner.

## Actionable Guidance

- If vLLM is already using around 50GB on an H100 80GB GPU, do not start with Qwen3-14B SFT. Use the low-VRAM 8B config first.
- Use `HF_HOME="$HOME/hf_cache"` when shared cache permissions are uncertain.
- Run a tiny committed PoC dataset before generating or copying larger processed data.
- Remember that `data/processed/train.jsonl` and `validation.jsonl` are not in Git. Generate them on the server or transfer them explicitly.
- Set `GITHUB_TOKEN` before collecting GitHub data if stable collection matters.
- Treat a completed training run as successful only when adapter files and `training_manifest.json` exist.
- Treat the current result as a pipeline success, not a final quality claim. Add held-out evaluation before claiming model improvement.
- For Qwen3 inference tests, use `/no_think` or `enable_thinking=False` when the expected output should not include reasoning traces.

Recommended environment setup for this shared-H100 path:

```bash
export PATH="$HOME/.local/bin:$PATH"
export HF_HOME="$HOME/hf_cache"
export HF_TOKEN_PATH="$HOME/.huggingface/token"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

Recommended low-VRAM training command:

```bash
uv run --system-certs python -m llm_tuning_lab.train.sft \
  --model-config configs/model/qwen3_8b_lowvram.yaml \
  --data-config configs/data/sft.yaml \
  --train-config configs/train/sft_lowvram.yaml \
  --lora-config configs/train/lora_lowvram.yaml \
  --output-dir outputs/sft/react-react-qwen3-8b-lowvram
```

## Evidence

- Related commit: `03fb5ae Add low-VRAM SFT preset`
- Related files:
  - `configs/model/qwen3_8b_lowvram.yaml`
  - `configs/train/sft_lowvram.yaml`
  - `configs/train/lora_lowvram.yaml`
  - `configs/run/react_react_qwen3_8b_lowvram.yaml`
- Successful output directory on the server:
  - `outputs/sft/react-react-qwen3-8b-lowvram/`
- Key output files:
  - `adapter_model.safetensors`
  - `adapter_config.json`
  - `checkpoint-15/`
  - `training_manifest.json`
- Final training metrics:
  - `train_runtime: 120.2`
  - `train_loss: 0.8628`
  - `mean_token_accuracy: 0.8757`
  - `epoch: 1`
- Generated split sizes:
  - train: 240
  - validation: 60
  - test: not generated

## Open Questions

- How much larger can the dataset become before this low-VRAM configuration becomes too slow or runs out of memory while vLLM is active?
- Would `Qwen/Qwen3-14B` fit if one or two vLLM processes were stopped, or if `max_seq_length` were reduced further?
- Does the LoRA adapter improve benchmark behavior compared with base model and RAG-only baselines?
- Should future Qwen3 SFT data include explicit no-thinking behavior, or should thinking be controlled only at inference time?
- Should the shared `/opt/jaicon_shared/hf_cache` permissions be fixed permanently for the team, or should each user keep a private cache to avoid collisions?
