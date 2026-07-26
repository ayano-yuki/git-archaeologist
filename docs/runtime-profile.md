# Runtime Profile

MVP では、Repository 固有の事実をモデルへ記憶させず、RAG の Evidence Pack を読むためにモデルを使う。実行環境の制約は、学習や推論の前に固定して記録する。

## 記録するもの

- CPU、RAM、ディスク空き容量。
- NVIDIA GPU が使える場合は GPU 名と VRAM。
- Embedding、Reranker、Answer / Judge LLM の候補モデル。
- 量子化方式、最大コンテキスト長、batch size。
- 候補モデルごとの速度とピークメモリの実測結果。

## MVP 暫定モデル

| 役割 | モデル | 量子化 | 最大コンテキスト |
| --- | --- | --- | --- |
| Embedding | `BAAI/bge-m3` | `fp16-or-int8-runtime` | 8192 |
| Reranker | `BAAI/bge-reranker-v2-m3` | `fp16-or-int8-runtime` | 8192 |
| Answer / Judge LLM | `Qwen/Qwen2.5-Coder-7B-Instruct` | `4-bit LoRA-compatible local runtime` | 32768 |

Answer / Judge LLM の Evidence Pack 予算は最大 24k token を目安にし、回答生成と検証 prompt を含めて 32k token の上限に収める。
16GB 級のローカル環境では OS の報告値が 16GiB を少し下回る場合があるため、Answer / Judge LLM は 15GiB 以上を最低条件とし、GPU がない場合は低速 CPU 実行として実測で採否を決める。

## 実行方法

標準ライブラリだけで、現在のハードウェアと固定したモデル制約を JSON として出力できる。

```powershell
uv run python -m git_archaeologist.evaluation.runtime_profile
```

証明書エラーが出る環境では次を使う。

```powershell
uv --system-certs run python -m git_archaeologist.evaluation.runtime_profile
```

この出力をベンチマーク実行時の前提として保存する。モデル ID、量子化方式、最大コンテキスト長、受け入れ基準を変更する場合は、実測前に `runtime-profile-v1` とは別の profile version と変更理由を記録する。

Python API から、モデル別の run directory へ保存できる。

```python
from git_archaeologist.evaluation.runtime_profile import build_runtime_profile, write_runtime_profile

profile = build_runtime_profile()
write_runtime_profile(profile, model_name="Qwen/Qwen2.5-Coder-7B-Instruct")
```

## ベンチマーク方針

- Embedding: 代表的な PR、Review、Diff、Commit message chunk を 100 件 embedding し、warmup 後 10 秒以内を目標にする。
- Reranker: frozen MVP 評価セットから 50 組の question / evidence pair を rerank し、warmup 後 5 秒以内を目標にする。
- Answer / Judge LLM: 24k token の Evidence Pack から構造化回答を 1 件生成し、8 tokens/sec 以上、または回答 p95 30 秒以内を目標にする。

実測結果は、対象モデルの `data/<model-name>/eval/runtime-profile/` に置く。レビュー済みで秘密情報を含まない評価レポートは Git 管理対象にする。
ローカル実行時の raw profile と benchmark report は `data/<model-name>/runs/runtime-profile/` に置き、secret や private 情報を含まないことを確認したうえで Git 管理対象にする。

## Phase 5 chat E2E 性能計測

Phase 5 では、利用者の待ち時間を支配するチャット処理を段階別に計測する。対象は `target_resolution`、`search`、`rerank`、`answer_generation`、`citation_verification` で、各段階の latency、CPU 時間、RAM、取得できる環境では GPU 利用率と VRAM を `QueryTrace` に記録する。

本物のモデル学習や重い推論は性能計測の前提にしない。標準の runner は deterministic backend を使い、外部収集や本物モデル実行なしで JSON report と summary markdown を生成できる。

```powershell
uv run python -m git_archaeologist.evaluation.phase5_performance
```

証明書エラーが出る環境では次を使う。

```powershell
uv --system-certs run python -m git_archaeologist.evaluation.phase5_performance
```

GPU / VRAM カウンタが取得できない場合、該当フィールドは `null`、resource status は `unknown` または `partial` として記録し、計測自体は継続する。`nvidia-smi` の呼び出しを避けたい場合は `--no-gpu` を付ける。

出力先の既定値は `data/Qwen--Qwen2.5-Coder-7B-Instruct/runs/phase5-performance/` で、次の2ファイルを生成する。

- `phase5-performance.json`: case、stage record、p95、QueryTrace を含む機械可読 report。
- `phase5-performance.md`: p95 または代表値から見た bottleneck summary。

性能数値は OS、CPU/GPU、同時実行中のプロセス、GPU カウンタ取得可否に依存する。同じ runtime profile 内で比較し、異なる環境の絶対値を品質差として扱わない。

## Phase 5 モデル・索引最適化レポート

Phase 5 の最適化では、量子化、context圧縮、batching、Embedding cache、候補数、Rerank範囲を profile として構造化し、品質指標と速度指標を同じ JSON report で比較する。
標準実装は既に得られた実測値、または deterministic test fixture を入力として扱う。学習、本物モデルの重い推論、外部収集は行わない。

```powershell
uv run python -m git_archaeologist.evaluation.optimization_report
```

証明書エラーが出る環境では次を使う。

```powershell
uv --system-certs run python -m git_archaeologist.evaluation.optimization_report
```

出力先の既定値は `data/Qwen--Qwen2.5-Coder-7B-Instruct/runs/optimization-report/` で、次の2ファイルを生成する。

- `optimization-report.json`: 比較対象 profile、品質指標、速度指標、品質閾値、推薦/棄却理由、推奨 runtime profile を含む機械可読 report。
- `optimization-report.md`: 推薦結果と棄却理由を確認するための summary。

推薦判定では、次の条件をすべて満たす profile だけを候補にする。

- 実測または deterministic test result として `measured=true` で記録されている。
- Evidence recall、citation integrity、unsupported claim rate、risk precision、schema validation rate が固定した品質閾値を満たす。
- p95 latency と、指定されている場合は peak RAM の速度・資源目標を満たす。

品質基準を下回る profile や、まだ測定されていない profile は、速度が良くても recommended にはしない。棄却理由は JSON の `decisions[].rejection_reasons` に残し、選ばれた profile は `recommended_runtime_profile` として model ID、量子化、context長、batch size、Embedding cache、候補数、Rerank範囲を持つ。
