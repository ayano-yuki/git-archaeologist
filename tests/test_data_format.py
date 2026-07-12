from llm_tuning_lab.data.formatters import validate_messages_record, validate_preference_record


def test_valid_messages_record() -> None:
    record = {
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
    }

    assert validate_messages_record(record) == []


def test_messages_record_requires_assistant_message() -> None:
    record = {"messages": [{"role": "user", "content": "Hello"}]}

    assert "record must contain at least one assistant message" in validate_messages_record(record)


def test_valid_preference_record() -> None:
    record = {"prompt": "p", "chosen": "good", "rejected": "bad"}

    assert validate_preference_record(record) == []


def test_preference_record_requires_distinct_outputs() -> None:
    record = {"prompt": "p", "chosen": "same", "rejected": "same"}

    assert "chosen and rejected must differ" in validate_preference_record(record)
