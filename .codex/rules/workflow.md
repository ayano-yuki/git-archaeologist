# Workflow ルール

## Role の流れ

1. `git-archaeologist-dev` が入口になる。
2. 作業開始前に `git-archaeologist-manager` が内容を整理する。
3. Manager は対象 Issue、phase、受け入れ条件、依存関係、機能領域を確認する。
4. 未 Issue 化の作業は Issue 分解案と作成ゲートへ進める。
5. 実装可能な Issue は `git-archaeologist-member` へ渡す。
6. 独立した Issue は複数 Member で並列実行してよい。
7. PR 作成後は `git-archaeologist-reviewer` が一次レビューする。
8. PR merge 後は `git-archaeologist-cleanup` が後始末する。

## 並列実行条件

- Issue の受け入れ条件が独立している。
- 主要な変更ファイルや責務境界が衝突しない。
- 依存順が明確である。
- 対応する `project/<function-area>` branch が存在し、base として妥当である。

## 並列化しない条件

- Issue 粒度が大きすぎる。
- 同じファイルを広く変更する。
- 依存関係、親子関係、機能領域、受け入れ条件が曖昧である。
- PR topology が規約外になる可能性を排除できない。

## 完了条件

- Issue 作成作業は、作成後に parent / subIssues を確認して完了する。
- Member 作業は、commit、push、PR URL 取得まで完了する。
- push 済み branch に対応する PR がない状態は未完了とする。
- cleanup 作業は、remote/local branch、worktree、prune 後の状態確認まで完了する。
