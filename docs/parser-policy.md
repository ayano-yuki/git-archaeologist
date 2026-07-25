# Parser Policy

Issue #71 では、MVP の対象 Repository を `react/react` に限定し、Code / Symbol Index が使う言語と Parser の方針を固定する。

## MVP 対応言語

MVP でシンボル抽出対象にするのは、React の主要な source file として扱う次の拡張子に限定する。

| 言語 | 拡張子 | Parser 方針 | シンボル抽出 |
| --- | --- | --- | --- |
| TypeScript | `.ts` | `tree-sitter-typescript` の `typescript` grammar | 対応 |
| TSX | `.tsx` | `tree-sitter-typescript` の `tsx` grammar | 対応 |
| JavaScript | `.js`, `.mjs`, `.cjs` | `tree-sitter-javascript` | 対応 |
| JSX | `.jsx` | JSX 対応の JavaScript grammar | 対応 |

抽出対象は、関数、クラス、メソッド、export された symbol、hook / component として参照できる宣言を想定する。実際の抽出実装では、文字列推測ではなく AST node range を source of truth にする。

## File Level Only

`.json`, `.json5`, `.md`, `.mdx`, `.yaml`, `.yml` は、MVP では file / snippet / diff hunk 単位の検索対象に留める。設定ファイルやドキュメントは根拠になり得るが、関数・クラス単位の Symbol Index は作らない。

## Fallback

対応拡張子でも parser が未導入、利用不能、または信頼できる AST を返せない場合は、symbol extraction を停止し、次の決定的な候補生成だけを許可する。

- repository relative path match
- exact code snippet match
- normalized code snippet match
- diff hunk match
- `git log -S` / `git log -G`
- 候補一覧の提示と利用者への確認

この fallback では、関数境界やクラス境界を正規表現、brace count、LLM の推測だけで確定しない。

## Unsupported Languages

上記以外の拡張子は MVP の Symbol Index では unsupported とする。unsupported file については、言語を推測して symbol を作らず、必要に応じて supported source file、正確な code snippet、または line / diff hunk context の提示を求める。

## No LLM Guessing

LLM は parser 対応可否、symbol boundary、複数候補からの単独選択を推測してはいけない。LLM が扱えるのは、parser または決定的 matching が生成した候補の説明に限定する。
