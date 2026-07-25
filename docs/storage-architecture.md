# Storage Architecture

MVP はローカル実行を前提にし、外部サービスなしで Raw Archive、共通イベント、全文検索、ベクトル検索、関係情報を再構築できる構成にする。

## 方針

- アプリケーションは Python package と CLI を中心にする。
- Runtime data は `data/local-runtime/` に置き、Git 管理対象にしない。
- レビュー済みの SFT / eval データだけを `data/<model-name>/sft/` と `data/<model-name>/eval/` にコピーして Git 管理対象にする。
- Raw Archive は不変データとして保存し、正規化や索引は再構築可能にする。

## 保存先

| 役割 | Backend | Path | 再構築 |
| --- | --- | --- | --- |
| Raw Archive | content-addressed JSON files | `data/local-runtime/raw/<repository-id>/<artifact-kind>/<external-id>.json` | 不可 |
| Manifest | SQLite | `data/local-runtime/processed/git-archaeologist.sqlite3` | 可 |
| Event Store | SQLite | `data/local-runtime/processed/git-archaeologist.sqlite3` | 可 |
| Full-text Index | SQLite FTS5 | `data/local-runtime/processed/git-archaeologist.sqlite3` | 可 |
| Vector Index | SQLite-compatible sidecar | `data/local-runtime/processed/vector-index/` | 可 |
| Graph Store | SQLite edge tables | `data/local-runtime/processed/git-archaeologist.sqlite3` | 可 |
| Evidence Packs | JSONL | `data/local-runtime/evidence-packs/<query-id>.jsonl` | 可 |
| Run Outputs | JSON / Markdown | `data/local-runtime/runs/<run-id>/` | 不可 |

## 初期化

保存先の構成はコードから確認できる。

```powershell
uv run python -m git_archaeologist.config.storage_config
```

Python API から空の保存先を作る。

```python
from git_archaeologist.config.storage_config import ensure_storage_layout

ensure_storage_layout("data/local-runtime")
```

## Vector Index

MVP 初期では vector backend を差し替え可能な sidecar として扱う。Embedding の実測結果と依存追加の承認後に、SQLite 拡張、FAISS、または軽量なファイルベース index のいずれかへ固定する。chunk ID、embedding model version、vector dimension、source event ID は backend に依存しないメタデータとして SQLite 側に保持する。

## 再構築

空の環境では次の順に再構築する。

1. Repository config を読む。
2. `ensure_storage_layout()` で保存先を作る。
3. GitHub / git から Raw Archive を収集する。
4. Raw Archive manifest を作る。
5. 共通イベントと関係 edge を生成する。
6. FTS5 と vector index を作る。
7. Evidence Pack と評価 run を生成する。

Raw Archive と run outputs は再取得または再実行が必要なため、削除前に人間確認ゲートを通す。
