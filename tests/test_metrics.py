from llm_tuning_lab.eval.metrics import evaluate_prediction, exact_match


def test_exact_match_strips_outer_whitespace() -> None:
    assert exact_match(" hello\n", "hello")


def test_evaluate_prediction_scores_citations_and_timeline() -> None:
    expected = {
        "citations": ["e1", "e2"],
        "timeline": [{"date": "2026-01-01T00:00:00Z"}],
        "uncertainty": "Some context is missing.",
    }
    prediction = {
        "facts": [{"text": "Fact", "citations": ["e1"]}],
        "citations": ["e1", "invented"],
        "timeline": [
            {"date": "2026-01-01T00:00:00Z", "text": "First", "citations": ["e1"]},
            {"date": "2026-01-02T00:00:00Z", "text": "Second", "citations": ["e2"]},
        ],
        "inference": "Likely reason.",
        "uncertainty": "This is uncertain.",
        "answer": "Answer.",
    }

    metrics = evaluate_prediction(prediction, expected)

    assert metrics["citation_precision"] == 0.5
    assert metrics["citation_recall"] == 0.5
    assert metrics["unsupported_citations"] == ["invented"]
    assert metrics["timeline_order"] is True
    assert metrics["schema_valid"] is True


def test_evaluate_prediction_rejects_empty_timeline_order() -> None:
    metrics = evaluate_prediction(
        {
            "facts": [],
            "citations": [],
            "timeline": [],
            "inference": "",
            "uncertainty": "",
            "answer": "",
        },
        {"citations": [], "timeline": []},
    )

    assert metrics["timeline_order"] is False


def test_evaluate_prediction_flags_uncautious_insufficient_evidence() -> None:
    metrics = evaluate_prediction(
        {
            "citations": [],
            "timeline": [],
            "uncertainty": "",
            "answer": "This definitely proves the rationale.",
        },
        {"citations": [], "timeline": [], "insufficient_evidence": True},
    )

    assert metrics["insufficient_evidence_caution"] is False
