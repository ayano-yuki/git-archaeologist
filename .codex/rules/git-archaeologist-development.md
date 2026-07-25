# Git Archaeologist 開発ルール

## Issue 運用

- 親 PBI Issue は `ayano-yuki/ayano-yuki-pbi#58` とする。
- 子 Issue タイトルは `【git-archaeologist 】 <内容>` 形式にする。
- 子 Issue は Manager Codex が一括で案を作り、人間が微調整してから `gh` で作成する。
- 子 Issue は Member Codex が迷わず着手できる粒度にする。

## 開発環境とディレクトリ

- Python 開発は `uv` を使う。
- 証明書エラーで `uv run` が失敗する環境では `uv --system-certs run ...` を使う。
- Python コードは `src/` 配下に置く。
- パッケージコードは `src/git_archaeologist/` 配下に置く。
- 学習・評価・実験用データは `data/` 配下に置く。
- `data/` はモデルごとにフォルダーを分ける。
- `data/<model-name>/` の構造は `data/README.md` に従う。
- `data/` 配下の生データ、教師データ、モデル出力、評価ログは原則 Git に含めない。

## 子 Issue の必須項目

子 Issue には次を含める。

- タイトル
- 背景
- 実装内容
- 受け入れ条件
- 触る想定ファイル
- テスト方針
- 依存 Issue
- 優先度
- Member への作業指示
- PR 作成時の注意点

## ブランチルール

- `phase/1-mvp` は MVP フェーズの統合ブランチとして扱う。
- `project/<function-area>` は機能領域の統合ブランチとして扱う。
- `feature/<issue-number>-<short-title>` は Member の作業ブランチとして扱う。
- 並列作業では `git worktree` を使い、Issue ごとに作業ディレクトリを分ける。
- 同じ worktree で別 Issue の作業を混ぜない。

## 機能領域

`project/<function-area>` は次の固定値から選ぶ。

- `collector`: GitHub / git 履歴収集、Raw Archive、認証・権限検査。
- `normalizer`: 共通イベント、Normalizer、Event Graph、関係生成。
- `search`: Code / Symbol Index、Hybrid Search、Target Resolver。
- `rag`: Evidence Pack、Reranker、Answer / Judge LLM、Citation Verifier。
- `chat`: Input Interpreter、チャット UI / API、会話状態。
- `evaluation`: 評価セット、品質指標、回帰評価、性能計測。

## コミットルール

コミットメッセージは `接頭語: 日本語の内容` 形式にする。

推奨接頭語:

- `feat`: 機能追加
- `fix`: 不具合修正
- `test`: テスト追加・修正
- `docs`: ドキュメント
- `refactor`: 振る舞いを変えない整理
- `chore`: 設定・雑務

例:

```text
feat: GitHub Artifact Collectorの基本構造を追加
test: Raw Archive manifestの検証ケースを追加
docs: Issue分解テンプレートを追加
```

## PR ルール

- PR タイトルは `[機能] PR内容（#issue番号）` とする。
- PR 本文には `- [issue] #123` の形式で関連 Issue を記載する。
- PR 作成前に、受け入れ条件、テスト結果、設計ズレの有無をまとめて人間確認を受ける。
- PR 作成後、人間レビュー前に Manager Codex が一次レビューする。

## 停止ルール

次の操作前には停止して、人間に確認内容を提示する。

- 子 Issue の一括作成。
- PR 作成。
- 新しい依存関係の追加。
- 設定ファイル、CI/CD、GitHub Actions、認証、秘密情報、保存場所の変更。
- 破壊的 git 操作。
- 大量削除、移動、リネーム。
- `docs/plan.md` または `docs/Todo.md` のロードマップ変更。

