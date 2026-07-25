# Issue 一括作成計画テンプレート

## 親 Issue

- 親 Issue: ayano-yuki/ayano-yuki-pbi#58
- phase Issue: ayano-yuki/ayano-yuki-pbi#<phase-issue-number>
- GitHub sub-issue: 作成する全実施 Issue を対応する phase Issue の sub-issue にする

## 一括作成の目的

この一括 Issue 作成で進めたい範囲を書く。

## 作成予定 Issue

| タイトル | 機能領域 | 優先度 | 依存 | 概要 |
| --- | --- | --- | --- | --- |
| 【git-archaeologist 】 <title> | collector | P1 | なし | <summary> |

## 設計ズレ確認

- [ ] 親 Issue の目的と合っている。
- [ ] 対応する phase Issue が存在する。存在しない場合は先に `--parent 58` で作成する。
- [ ] `docs/plan.md` のフェーズと合っている。
- [ ] `docs/Todo.md` の必須タスクと対応している。
- [ ] Issue が大きすぎない。
- [ ] 依存関係が明確。
- [ ] 実施 Issue の `gh issue create` コマンド案に `--parent <phase-issue-number>` が含まれている。

## gh コマンド案

人間確認後に実行する `gh issue create --parent <phase-issue-number>` コマンド案を書く。phase Issue が未作成の場合は、先に `gh issue create --parent 58` で phase Issue を作成するコマンド案を書く。

## 作成後確認

作成後に親 Issue #58 の `subIssues`、phase Issue の `subIssues`、または各子 Issue の `parent` を確認するコマンド案を書く。
