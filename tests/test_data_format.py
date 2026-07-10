from llm_tuning_lab.data.formatters import validate_messages_record


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
