# Data / Layout ルール

## 開発環境

- Python 開発は `uv` を使う。
- 証明書エラーで `uv run` が失敗する環境では `uv --system-certs run ...` を使う。

## ディレクトリ

- Python コードは `src/` 配下に置く。
- パッケージコードは `src/git_archaeologist/` 配下に置く。
- 学習・評価・実験用データは `data/` 配下に置く。
- `data/` はモデルごとにフォルダーを分ける。
- `data/<model-name>/` の構造は `data/README.md` に従う。

## Data 管理

- `data/` 配下の生データ、モデル出力、評価ログ、runtime output は Git 管理対象にする。
- 個人情報、秘密情報、private repository 固有情報、未 redacted の生 artifact は `data/` に置かない。
