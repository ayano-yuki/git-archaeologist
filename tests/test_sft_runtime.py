from llm_tuning_lab.train.sft_runtime import build_data_files


def test_build_data_files_with_train_only() -> None:
    data_files = build_data_files({"train_file": "data/samples/sft_sample.jsonl"})

    assert data_files == {"train": "data/samples/sft_sample.jsonl"}


def test_build_data_files_with_validation() -> None:
    data_files = build_data_files(
        {
            "train_file": "data/processed/train.jsonl",
            "validation_file": "data/processed/validation.jsonl",
        }
    )

    assert data_files == {
        "train": "data/processed/train.jsonl",
        "validation": "data/processed/validation.jsonl",
    }
