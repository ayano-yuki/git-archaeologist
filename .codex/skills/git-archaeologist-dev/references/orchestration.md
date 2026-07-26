# Git Archaeologist ルーティング補助

この reference は、`git-archaeologist-dev` が役割を選ぶときだけ読む。詳細ルールは `.codex/rules/`、実作業は role skill を優先する。

## 標準フロー

1. Dev Router が依頼を受ける。
2. Manager が作業内容を整理する。
3. Manager が Issue、phase、受け入れ条件、依存関係、機能領域、base branch を確認する。
4. 未 Issue 化の作業は Manager が Issue 作成案を作る。
5. 実装可能な Issue は Member に渡す。
6. 独立した Issue は複数 Member で並列に進める。
7. PR 作成後は Reviewer が一次レビューする。
8. PR merge 後は Cleanup が後始末する。

## Role 選択

- Manager: 整理、Issue 分解、親子関係修復、Member 割り当て。
- Member: 単一 Issue の実装、テスト、commit、push、PR 作成。
- Reviewer: PR topology、受け入れ条件、テスト、危険操作の確認。
- Cleanup: merge 済み PR の branch / worktree 削除。

## 並列化メモ

並列化できるのは、Issue の受け入れ条件、主要ファイル、機能領域、依存関係が衝突しない場合だけ。説明できない並列化はしない。

## 禁止

- Manager のまま実装する。
- Member が複数 Issue を束ねる。
- `feature -> main` PR を作る。
- `feature -> feature` stacked PR を作る。
- merge 確認前に branch / worktree を削除する。
