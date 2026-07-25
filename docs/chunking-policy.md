# Chunking Policy

MVP の検索単位は、固定長ではなく artifact の意味単位を優先する。
各 chunk は必ず親 event、source URL、順序、前後文脈へ戻れる情報を持つ。

## Artifact 別の規則

- PR body: 段落単位で分割し、長い段落だけ行単位へ fallback する。
- Review comment: コメント本文の段落単位で分割し、前後 chunk の短い context を保持する。
- Issue comment: Review comment と同じ規則を使う。
- Diff hunk: `@@` hunk header を境界として分割し、`file_path` を metadata に保持する。
- Commit message: subject と body を同一 chunk にまとめ、短い message は分割しない。

## 引用と復元性

chunk から回答引用に使うため、次を必須にする。

- `parent_event_id`: 共通イベントへ戻る ID。
- `source_url`: GitHub または commit URL。
- `sequence`: 同じ親 event 内の順序。
- `previous_context` / `next_context`: 分割境界の周辺確認用 context。

コンテキスト上限で一部 chunk だけを使う場合も、親 event と source URL が失われないようにする。
