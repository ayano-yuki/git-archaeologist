# gh コマンドテンプレート

実行前に `.codex/hooks/` の該当ゲートを確認する。`<function-area>` は `collector`、`normalizer`、`search`、`rag`、`chat`、`evaluation` のいずれかに置き換える。

## phase Issue 作成

```powershell
gh issue create `
  --repo ayano-yuki/ayano-yuki-pbi `
  --title "【git-archaeologist 】 phaseNN" `
  --body-file "<path-to-phase-body.md>" `
  --parent 58
```

## 実施 Issue 作成

phase 内で実施する Issue は、対応する phase Issue の sub-issue にする。

```powershell
gh issue create `
  --repo ayano-yuki/ayano-yuki-pbi `
  --title "【git-archaeologist 】 <title>" `
  --body-file "<path-to-generated-body.md>" `
  --parent <phase-issue-number>
```

## sub-issue 修復

既存の実施 Issue が親 PBI #58 直下にある場合は、対応する phase Issue の sub-issue へ修復する。

```powershell
gh issue edit <child-issue-number> `
  --repo ayano-yuki/ayano-yuki-pbi `
  --parent <phase-issue-number>
```

複数 Issue をまとめて修復する場合は、Issue 番号を並べる。

```powershell
gh issue edit 68 69 70 `
  --repo ayano-yuki/ayano-yuki-pbi `
  --parent <phase-issue-number>
```

## sub-issue 確認

Issue 作成または修復後、親 Issue または子 Issue から親子関係を確認する。

```powershell
gh issue view 58 `
  --repo ayano-yuki/ayano-yuki-pbi `
  --json number,title,subIssues

gh issue view <phase-issue-number> `
  --repo ayano-yuki/ayano-yuki-pbi `
  --json number,title,parent,subIssues

gh issue view <child-issue-number> `
  --repo ayano-yuki/ayano-yuki-pbi `
  --json number,title,parent
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
PR 本文の関連 Issue は `- [https://github.com/ayano-yuki/ayano-yuki-pbi/issues/123](https://github.com/ayano-yuki/ayano-yuki-pbi/issues/123)` のように、Issue URL をラベルにも使うリンク形式にする。

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

## merge 後 cleanup 確認

cleanup は `git-archaeologist-cleanup` と `.codex/hooks/post-merge-cleanup-gate.md` に従う。実行前に PR が merge 済みであることを確認する。

```powershell
gh pr view <pr-number> `
  --repo ayano-yuki/git-archaeologist `
  --json number,title,state,mergedAt,baseRefName,headRefName,headRepositoryOwner

git worktree list
git status --short --branch
```

削除対象は PR head branch に限定する。

```powershell
git worktree remove "<worktree-path>"
git branch -d "<head-branch>"
git push origin --delete "<head-branch>"
git fetch --prune origin
```
