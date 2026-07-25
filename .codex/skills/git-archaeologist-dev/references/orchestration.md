# Git Archaeologist オーケストレーション

この reference は、Git Archaeologist を Codex Manager / Member で並列開発するための運用手順をまとめる。詳細なルールは `.codex/rules/git-archaeologist-development.md` と `.codex/hooks/` を優先する。

## 運用モデル

- 人間: 親 Issue、子 Issue 案、PR 作成前の設計ズレ、人間レビュー、マージ判断を担当する。
- Manager Codex: Issue 分解、子 Issue 作成準備、Member 割り当て、PR 一次レビュー、レビュー指摘の再割り当てを担当する。
- Member Codex: 割り当てられた Issue の実装、テスト、コミット、PR 作成を担当する。

## 親 Issue

- 親 PBI: `ayano-yuki/ayano-yuki-pbi#58`
- 子 Issue タイトル形式: `【git-archaeologist 】 <title>`

## 全体フロー

1. Manager Codex が親 Issue、`docs/plan.md`、`docs/Todo.md` を読む。
2. Manager Codex が `.codex/orchestration/templates/child-issue.md` で子 Issue 案を作る。
3. Manager Codex が `.codex/orchestration/templates/issue-batch-plan.md` で一括作成計画を作る。
4. Manager Codex が `.codex/hooks/issue-create-gate.md` で停止する。
5. 人間が一括作成計画を修正または承認する。
6. Manager Codex が `gh issue create` コマンドを準備または実行する。
7. Manager Codex が各 Issue を Member Codex へ割り当てる。
8. Member Codex が Issue 専用の `git worktree` を作る。
9. Member Codex が実装、テスト、コミットを行う。
10. Member Codex が `.codex/orchestration/templates/pr.md` で PR 本文を作る。
11. Member Codex が `.codex/hooks/pr-create-gate.md` で停止する。
12. 人間が Issue 設計からズレていないかを確認する。
13. Member Codex が feature ブランチを push し、PR を作成する。push だけで停止した状態は未完了とする。
14. Manager Codex が push 済み feature ブランチと open PR の対応を確認し、PR 作成漏れがあれば作成する。
15. Manager Codex が人間レビュー前の一次レビューを行う。
16. 人間が PR をレビューする。
17. Manager Codex がレビュー指摘を元 Member または別 Member へ再割り当てする。

## ブランチモデル

ブランチ階層は次を使う。

```text
main
phase/1-mvp
project/<function-area>
feature/<issue-number>-<short-title>
```

PR の向き先は隣接階層だけに限定する。

- `project/<function-area>` から `main`。
- `feature/<issue-number>-<short-title>` から対応する `project/<function-area>`。
- `feature` から `main`、`feature` から別 `feature`、`project` から `feature` への PR は作らない。

使える機能領域:

- `collector`
- `normalizer`
- `search`
- `rag`
- `chat`
- `evaluation`

## 開発配置

- Python 開発は `uv` を使う。
- 証明書エラーで `uv run` が失敗する環境では `uv --system-certs run ...` を使う。
- コードは `src/` 配下に置く。
- パッケージコードは `src/git_archaeologist/` 配下に置く。
- 学習・評価・実験用データは `data/` 配下に置く。
- `data/` 配下はモデルごとに `data/<model-name>/` で分ける。
- モデル別データの詳細構造は `data/README.md` に従う。

## 人間確認ゲート

次の操作前には必ず停止する。

- 子 Issue の作成。
- PR 作成。
- 依存関係の追加。
- CI/CD、GitHub Actions、認証、秘密情報、権限、データ保存先の変更。
- 破壊的 git 操作。
- 大量の削除、移動、リネーム。
- `docs/plan.md` または `docs/Todo.md` のロードマップ範囲変更。

分割済みの hook reference:

- `.codex/hooks/issue-create-gate.md`
- `.codex/hooks/pr-create-gate.md`
- `.codex/hooks/dangerous-operation-gate.md`

## Manager 一次レビュー

人間レビュー前に Manager Codex は次を確認する。

- PR が Issue の受け入れ条件を満たしている。
- push 済み feature ブランチに対応する PR が作成されている。
- 差分が Issue の範囲内に収まっている。
- テストが Issue のテスト方針と合っている。
- ブランチ、PR の向き先、コミット、PR タイトル、PR 本文が規約に合っている。
- 危険操作が人間確認ゲートを通っている。
- 変更が `docs/plan.md` または `docs/Todo.md` と矛盾していない。

## レビュー指摘のトリアージ

レビュー指摘が来たら次の順で扱う。

1. コメントとチェック結果を読む。
2. 必要な修正単位で指摘をまとめる。
3. 元 Member に戻すか、別 Member に割り当てるかを決める。
4. 設計変更を伴う指摘は人間確認ゲートで止める。
5. 追加コミットまたは追加 PR が元 Issue を参照していることを確認する。
