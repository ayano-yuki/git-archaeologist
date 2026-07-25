# Issue 一括作成計画テンプレート

## 親 Issue

- 親 Issue: ayano-yuki/ayano-yuki-pbi#58
- GitHub sub-issue: 作成する全 Issue を #58 の sub-issue にする

## 一括作成の目的

この一括 Issue 作成で進めたい範囲を書く。

## 作成予定 Issue

| タイトル | 機能領域 | 優先度 | 依存 | 概要 |
| --- | --- | --- | --- | --- |
| 【git-archaeologist 】 <title> | collector | P1 | なし | <summary> |

## 設計ズレ確認

- [ ] 親 Issue の目的と合っている。
- [ ] `docs/plan.md` のフェーズと合っている。
- [ ] `docs/Todo.md` の必須タスクと対応している。
- [ ] Issue が大きすぎない。
- [ ] 依存関係が明確。
- [ ] `gh issue create` コマンド案に `--parent 58` が含まれている。

## gh コマンド案

人間確認後に実行する `gh issue create --parent 58` コマンド案を書く。

## 作成後確認

作成後に親 Issue #58 の `subIssues` または各子 Issue の `parent` を確認するコマンド案を書く。
