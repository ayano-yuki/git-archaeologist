# Evidence Pack

Evidence Pack は、生成 LLM に渡す根拠を citation 可能な item だけへ制限するための構造化 payload です。

- `question`: 利用者の質問。
- `target`: file、symbol、commit、snippet で表した対象コード。
- `items`: source URL と parent event ID へ戻れる根拠。
- `omitted`: token budget により除外した根拠と理由。
- `pack_id`: 同じ質問、対象、採用 item、token budget から再現できる ID。

Token budget 超過時は `direct`、`related`、`weak` の順で優先し、同じ強さなら token 数が小さい item を先に採用する。
