from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


class Phase5LimitationsDocsTest(unittest.TestCase):
    def test_limitations_doc_separates_guarantees_from_non_goals(self) -> None:
        text = read_text("docs/limitations.md")

        for phrase in (
            "保証していること",
            "保証していないこと",
            "取得済みの Commit、PR、Issue、Review、CI、Revert",
            "外部会話",
            "推測で補わない",
            "削除済み",
            "shallow clone",
            "対応言語外",
            "因果関係",
            "原因として断定しない",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_limitations_doc_lists_unanswerable_conditions_and_checks(self) -> None:
        text = read_text("docs/limitations.md")

        for phrase in (
            "回答不能となる代表条件と確認方法",
            "根拠不足",
            "synced_at",
            "watermarks",
            "Raw Archive",
            "Current Change Context",
            "lineage confidence",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_limitations_doc_links_phase5_troubleshooting_entries(self) -> None:
        text = read_text("docs/limitations.md")

        expected_links = (
            "../README.md#セットアップ確認",
            "../README.md#同期状態確認",
            "./Todo.md#52-ローカル運用と配布",
            "./Todo.md#54-最終品質保証",
            "./parser-policy.md",
        )
        for link in expected_links:
            with self.subTest(link=link):
                self.assertIn(link, text)

    def test_readme_and_todo_point_to_limitations_docs(self) -> None:
        readme = read_text("README.md")
        todo = read_text("docs/Todo.md")

        self.assertIn("docs/limitations.md", readme)
        self.assertIn("[x] **必須: 制約と非対応範囲を文書化する**", todo)
        self.assertIn("setup / sync / data protection / regression", todo)


if __name__ == "__main__":
    unittest.main()
