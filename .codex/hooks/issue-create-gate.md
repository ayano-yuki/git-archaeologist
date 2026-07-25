# Issue 作成前ゲート

親 PBI から子 GitHub Issue を作成する前に使う確認ゲート。

## 発火条件

次の操作前に停止する。

- `gh issue create`
- `gh issue create` を呼ぶ一括作成スクリプト
- GitHub API による Issue 作成

## 提示する情報

Manager Codex は次を人間に提示する。

- 親 Issue: `ayano-yuki/ayano-yuki-pbi#58`
- 子 Issue は親 Issue #58 の GitHub sub-issue として作成すること
- 一括作成の目的
- 子 Issue 一覧
- 各 Issue の機能領域
- 各 Issue の優先度
- Issue 間の依存関係
- 各 Issue の受け入れ条件
- `--parent 58` を含む `gh issue create` コマンド案、または一括作成に使う入力内容
- 既存 Issue を修復する場合は `gh issue edit <issue-number> --parent 58` のコマンド案
- 作成後または修復後の sub-issue 確認コマンド

## 人間レビュー観点

人間に次を確認してもらう。

- 一括作成案が親 Issue の意図と合っている。
- 各 Issue が親 Issue #58 の GitHub sub-issue として作成または修復される。
- 各 Issue が `docs/plan.md` と `docs/Todo.md` に対応している。
- 各 Issue が 1 つの Member Codex で扱える大きさである。
- 依存関係が明確で、順序が逆転していない。
- 機能領域が `collector`、`normalizer`、`search`、`rag`、`chat`、`evaluation` のいずれかである。
- Issue タイトルが `【git-archaeologist 】 <title>` 形式である。

## 再開条件

人間が一括作成または sub-issue 修復を承認した後にだけ進める。修正指示があった場合は、一括作成案を直して再提示してから Issue を作成する。作成後または修復後は、親 Issue #58 の `subIssues` か子 Issue の `parent` を確認する。
