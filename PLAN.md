# Git Archaeologist

**コードではなく、ソフトウェアの歴史を理解するローカル LLM**

Git Archaeologist は、現在のコードやドキュメントだけでなく、Commit、PR、Issue、Review、Revert、CI ログなどの履歴を根拠として参照し、**「なぜこのコードになったのか」**を説明できる AI を目指すプロジェクトです。

## 解決したい課題

開発が進むほど、コードの背景にある設計理由は失われやすくなります。

- なぜこの実装なのか
- なぜ別案を採用しなかったのか
- この変更をすると何が壊れるのか

こうした疑問は、現在のコードだけを見ても十分に答えられません。開発者が退職したり、議論が Issue や PR に分散したりすると、設計判断の文脈はさらに見えにくくなります。

Git Archaeologist は、その失われがちな設計理由を AI で復元します。

## 基本方針

このプロジェクトの中心方針は、**知識は RAG、推論は Fine-tuning** です。

GitHub の履歴そのものをモデルに記憶させるのではなく、事実知識は RAG で参照します。Fine-tuning では、履歴から設計意図、因果関係、暗黙知を読み解く推論様式を学習させます。

### RAG で扱う知識

- ソースコード
- Commit
- PR
- Issue
- Review
- Release Note
- CI
- blame

### Fine-tuning で学習する推論様式

- Issue から PR への対応関係
- 設計判断
- Revert 理由
- 障害原因
- レビューの思考
- 根拠の示し方

## できること

| ユースケース | 質問例 | 期待する回答 |
| --- | --- | --- |
| Why | なぜこう実装した？ | Issue、PR、Review などの根拠を示しながら、実装理由を説明する |
| Risk | この修正は危険？ | 過去の類似変更や障害履歴をもとに、壊れやすい箇所を説明する |
| Lost Knowledge | このコードの暗黙ルールは？ | 履歴から読み取れる運用上の制約や設計上の前提を説明する |
| Historical Similarity | この PR は過去の何に似ている？ | 類似する PR や失敗例を挙げ、共通点を説明する |
| Decision Reconstruction | この設計はどういう議論だった？ | Issue、PR、Review の流れを時系列で整理する |

## 画面イメージ

回答は、どこから来た情報なのかを追跡できる形にします。

```text
質問
  ↓
AI回答
  ↓
根拠
  ↓
Issue
  ↓
PR
  ↓
Commit
  ↓
Review
  ↓
Timeline
```

## 差別化

普通の AI は、主に現在のコードを見ます。

```text
現在のコードを見る
```

Git Archaeologist は、コードが今の形になった歴史を見ます。

```text
コードの歴史を見る
```

## 技術構成

```text
GitHub
  ↓
Parser
  ↓
Knowledge Graph
  ↓
Embedding
  ↓
RAG
  ↓
Local LLM
  ↓
Fine-tuning
  ↓
UI
```

## Fine-tuning する内容

重要なのは、GitHub を覚えさせることではありません。

モデルに覚えさせるのは、履歴そのものではなく、履歴から以下を読み解く方法です。

- 設計判断
- 原因分析
- 根拠引用
- 障害分析
- レビュー思考

## 評価方法

比較対象を分けることで、RAG と Fine-tuning の役割を検証します。

### 比較対象

- GPT
- RAG のみ
- Fine-tuning のみ
- RAG + Fine-tuning

### 評価指標

- 根拠正確率
- Issue 特定率
- PR 特定率
- 幻覚率
- 障害検出率
- 説明品質

## ロードマップ

### MVP

- GitHub 取得
- RAG
- Timeline UI
- Why 回答

### 完成版

- Fine-tuning
- 類似障害検出
- Revert 検出
- 歴史再構築
- Knowledge Graph
- 複数 Repository 対応

## 一番重要な価値

このプロジェクトは、「GitHub を学習した AI」を作ることではありません。

**コードベースに埋もれた設計知識を復元する AI を作ること**が目的です。

そのため、ファインチューニングの対象は履歴そのものではなく、履歴から設計意図、因果関係、暗黙知を推論する能力です。ここが実現できれば、「RAG だけでは足りない理由」を明確に示せるプロジェクトになります。
