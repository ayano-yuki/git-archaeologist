# gh コマンドテンプレート

実行前に `.codex/hooks/` の該当ゲートを確認する。`<function-area>` は `collector`、`normalizer`、`search`、`rag`、`chat`、`evaluation` のいずれかに置き換える。

## Issue 作成

```powershell
gh issue create `
  --repo ayano-yuki/ayano-yuki-pbi `
  --title "【git-archaeologist 】 <title>" `
  --body-file "<path-to-generated-body.md>"
```

## Issue 一覧

```powershell
gh issue list `
  --repo ayano-yuki/ayano-yuki-pbi `
  --search "git-archaeologist in:title"
```

## project ブランチ作成

```powershell
git switch phase/1-mvp
git switch -c project/<function-area>
git push -u origin project/<function-area>
```

## worktree 作成

```powershell
git fetch origin
git worktree add "..\git-archaeologist-issue-<issue-number>" -b "feature/<issue-number>-<short-title>" "origin/project/<function-area>"
```

## feature ブランチ push

PR 作成前ゲートで人間確認を受けたあと、PR 作成前に feature ブランチを push する。

```powershell
git push -u origin feature/<issue-number>-<short-title>
```

## PR 作成

PR 作成前ゲートで人間確認を受け、隣接階層だけに PR を作成する。

- feature 作業は `project/<function-area>` を base にする。
- project 統合は `main` を base にする。

feature ブランチを push してから実行する。

```powershell
gh pr create `
  --repo ayano-yuki/git-archaeologist `
  --base "project/<function-area>" `
  --head "feature/<issue-number>-<short-title>" `
  --title "[機能] PR内容（#123）" `
  --body-file "<path-to-pr-body.md>"
```

project ブランチを main へ統合する PR は次を使う。

```powershell
gh pr create `
  --repo ayano-yuki/git-archaeologist `
  --base "main" `
  --head "project/<function-area>" `
  --title "[機能] PR内容（#123）" `
  --body-file "<path-to-pr-body.md>"
```

## PR 確認

```powershell
gh pr view <pr-number> --repo ayano-yuki/git-archaeologist
gh pr checks <pr-number> --repo ayano-yuki/git-archaeologist
```
