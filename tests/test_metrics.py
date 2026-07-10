from llm_tuning_lab.eval.metrics import exact_match


def test_exact_match_strips_outer_whitespace() -> None:
    assert exact_match(" hello\n", "hello")
