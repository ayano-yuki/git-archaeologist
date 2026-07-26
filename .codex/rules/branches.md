# Branch / Worktree ルール

## Branch 階層

```text
main
phase/1-mvp
project/<function-area>
feature/<issue-number>-<short-title>
```

- `phase/1-mvp` は MVP フェーズの統合ブランチとして扱う。
- `project/<function-area>` は機能領域の統合ブランチとして扱う。
- `feature/<issue-number>-<short-title>` は Member の作業ブランチとして扱う。

## Worktree

- 並列作業では `git worktree` を使い、Issue ごとに作業ディレクトリを分ける。
- 同じ worktree で別 Issue の作業を混ぜない。
- Member は対応する `project/<function-area>` から `feature/<issue-number>-<short-title>` を作る。
- 対応する `project/<function-area>` が存在しない、不明、古い場合は、feature branch を作らず Manager に戻す。

## PR topology

- PR の向き先は隣接階層だけに限定する。
- `project/<function-area>` の PR は `main` を base、`project/<function-area>` を head にする。
- `feature/<issue-number>-<short-title>` の PR は対応する `project/<function-area>` を base、feature branch を head にする。
- `feature` から `main`、`feature` から別 `feature`、`project` から `feature` への PR は作らない。
- 依存 Issue があっても stacked `feature -> feature` PR は作らない。依存関係は Issue とレビュー順で管理する。
- PR 作成前に base/head を確認し、規約外なら `gh pr create` を実行せず停止する。
