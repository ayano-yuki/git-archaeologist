from llm_tuning_lab.train.accounting import compute_accounting, validate_serious_gates


class WordTokenizer:
    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return list(range(len(text.split())))


def test_messages_token_stats() -> None:
    records = [
        {
            "messages": [
                {"role": "user", "content": "one two"},
                {"role": "assistant", "content": "three four five"},
            ]
        },
        {
            "messages": [
                {"role": "system", "content": "rules"},
                {"role": "user", "content": "six"},
                {"role": "assistant", "content": "seven eight"},
            ]
        },
    ]

    stats = compute_accounting(
        records,
        tokenizer=WordTokenizer(),
        max_seq_length=16,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=2,
    )

    assert stats.record_count == 2
    assert stats.total_tokens == 14
    assert stats.target_tokens == 5
    assert stats.p50_length == 7
    assert stats.p95_length == 7
    assert stats.max_length == 7
    assert stats.effective_batch_size == 2
    assert stats.estimated_optimizer_steps == 1
    assert stats.tokens_per_step == 14
    assert stats.expected_total_trained_tokens == 14


def test_dpo_token_stats() -> None:
    records = [
        {"prompt": "one two", "chosen": "three four five", "rejected": "six"},
        {"prompt": "seven", "chosen": "eight", "rejected": "nine ten eleven twelve"},
    ]

    stats = compute_accounting(
        records,
        tokenizer=WordTokenizer(),
        max_seq_length=8,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=1,
        max_steps=5,
    )

    assert stats.record_count == 2
    assert stats.total_tokens == 12
    assert stats.target_tokens == 9
    assert stats.p50_length == 5
    assert stats.p95_length == 5
    assert stats.estimated_optimizer_steps == 5
    assert stats.tokens_per_step == 6
    assert stats.expected_total_trained_tokens == 30


def test_over_length_detection() -> None:
    records = [
        {"prompt": "one two", "chosen": "three", "rejected": "four"},
        {"prompt": "one two three four", "chosen": "five six", "rejected": "seven eight nine"},
    ]

    stats = compute_accounting(records, tokenizer=WordTokenizer(), max_seq_length=6)

    assert stats.max_length == 7
    assert stats.over_max_length_count == 1


def test_min_token_and_count_gate() -> None:
    stats = compute_accounting(
        [{"prompt": "one", "chosen": "two", "rejected": "three"}],
        tokenizer=WordTokenizer(),
        max_seq_length=4,
    )

    errors = validate_serious_gates(
        stats,
        validation_record_count=0,
        min_records=2,
        min_target_tokens=10,
        max_seq_length=4,
        gpu_vram_gb=80,
        model_tier="h100_80gb",
    )

    assert "record_count 1 is below required minimum 2." in errors
    assert "target_tokens 2 is below required minimum 10." in errors
    assert "validation set must contain at least one record." in errors


def test_top_tier_small_gpu_fail() -> None:
    stats = compute_accounting(
        [{"prompt": "one", "chosen": "two", "rejected": "three"}],
        tokenizer=WordTokenizer(),
        max_seq_length=4,
    )

    errors = validate_serious_gates(
        stats,
        validation_record_count=1,
        min_records=1,
        min_target_tokens=1,
        max_seq_length=4,
        gpu_vram_gb=80,
        model_tier="top",
    )

    assert "top model tier requires gpu_vram_gb >= 160." in errors
