from llm_tuning_lab.eval.metrics import evaluate_prediction, exact_match


def test_exact_match_strips_outer_whitespace() -> None:
    assert exact_match(" hello\n", "hello")


def test_evaluate_prediction_scores_citations_and_timeline() -> None:
    expected = {
        "facts": [{"text": "Fact", "citations": ["e1"]}],
        "citations": ["e1", "e2"],
        "timeline": [{"date": "2026-01-01T00:00:00Z", "text": "First", "citations": ["e1"]}],
        "inference": "Likely reason.",
        "uncertainty": "Some context is missing.",
        "answer": "Answer.",
    }
    prediction = {
        "schema_version": "git-archaeologist.answer.v1",
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
    assert metrics["fact_recall"] == 1.0
    assert metrics["answer_similarity"] == 1.0


def test_evaluate_prediction_rejects_empty_timeline_order() -> None:
    metrics = evaluate_prediction(
        {
            "schema_version": "git-archaeologist.answer.v1",
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
    assert metrics["schema_valid"] is False


def test_evaluate_prediction_scores_content_mismatch_low() -> None:
    metrics = evaluate_prediction(
        {
            "schema_version": "git-archaeologist.answer.v1",
            "facts": [{"text": "The change was only personal preference.", "citations": ["e1"]}],
            "citations": ["e1"],
            "timeline": [
                {
                    "date": "2026-01-03T00:00:00Z",
                    "text": "A different event happened.",
                    "citations": ["e1"],
                }
            ],
            "inference": "The author simply liked this implementation.",
            "uncertainty": "Some context may be missing.",
            "answer": "The reason was preference.",
        },
        {
            "facts": [{"text": "The PR kept synchronous auth to avoid refresh races.", "citations": ["e1"]}],
            "citations": ["e1"],
            "timeline": [
                {
                    "date": "2026-01-01T00:00:00Z",
                    "text": "The outage discussion identified refresh races.",
                    "citations": ["e1"],
                }
            ],
            "inference": "The implementation likely preserved ordering around refresh.",
            "uncertainty": "Offline context may be missing.",
            "answer": "Synchronous auth was kept to preserve token refresh ordering.",
        },
    )

    assert metrics["fact_recall"] == 0.0
    assert metrics["timeline_event_recall"] == 0.0
    assert metrics["answer_similarity"] < 0.35
    assert metrics["unsupported_claim_count"] > 0


def test_evaluate_prediction_flags_uncautious_insufficient_evidence() -> None:
    metrics = evaluate_prediction(
        {
            "schema_version": "git-archaeologist.answer.v1",
            "facts": [],
            "citations": [],
            "timeline": [],
            "inference": "",
            "uncertainty": "",
            "answer": "This definitely proves the rationale.",
        },
        {"citations": [], "timeline": [], "insufficient_evidence": True},
    )

    assert metrics["insufficient_evidence_caution"] is False
