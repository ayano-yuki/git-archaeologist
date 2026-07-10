from __future__ import annotations


def exact_match(prediction: str, expected: str) -> bool:
    return prediction.strip() == expected.strip()
