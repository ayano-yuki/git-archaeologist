from __future__ import annotations

from pathlib import Path
import unittest

from git_archaeologist.evaluation_splits import (
    EvaluationSplit,
    EvaluationSplitManifest,
    SplitManifestViolation,
    load_split_manifest,
)


MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "baseline-rag"
    / "eval"
    / "repository-specific"
    / "split-manifest.json"
)


class EvaluationSplitTests(unittest.TestCase):
    def test_seed_manifest_has_train_validation_test_and_time_windows(self) -> None:
        manifest = load_split_manifest(MANIFEST_PATH)

        self.assertIsInstance(manifest, EvaluationSplitManifest)
        self.assertEqual(
            {EvaluationSplit.TRAIN, EvaluationSplit.VALIDATION, EvaluationSplit.TEST},
            {entry.split for entry in manifest.entries},
        )
        self.assertTrue(all(entry.window is not None for entry in manifest.entries))

    def test_rejects_decision_overlap_across_splits(self) -> None:
        with self.assertRaises(SplitManifestViolation):
            EvaluationSplitManifest(
                schema_version=1,
                dataset_version="v1",
                source_repository="react/react",
                entries=(
                    _entry(EvaluationSplit.TRAIN, ("decision-a",), ("pr-1",)),
                    _entry(EvaluationSplit.TEST, ("decision-a",), ("pr-2",)),
                    _entry(EvaluationSplit.VALIDATION, ("decision-b",), ("pr-3",)),
                ),
            )

    def test_rejects_artifact_overlap_across_splits(self) -> None:
        with self.assertRaises(SplitManifestViolation):
            EvaluationSplitManifest(
                schema_version=1,
                dataset_version="v1",
                source_repository="react/react",
                entries=(
                    _entry(EvaluationSplit.TRAIN, ("decision-a",), ("pr-1",)),
                    _entry(EvaluationSplit.TEST, ("decision-b",), ("pr-1",)),
                    _entry(EvaluationSplit.VALIDATION, ("decision-c",), ("pr-3",)),
                ),
            )

    def test_rejects_missing_required_split(self) -> None:
        with self.assertRaises(SplitManifestViolation):
            EvaluationSplitManifest(
                schema_version=1,
                dataset_version="v1",
                source_repository="react/react",
                entries=(
                    _entry(EvaluationSplit.TRAIN, ("decision-a",), ("pr-1",)),
                    _entry(EvaluationSplit.TEST, ("decision-b",), ("pr-2",)),
                ),
            )


def _entry(split, decision_ids, artifact_ids):
    from git_archaeologist.evaluation_splits import DecisionSplit

    return DecisionSplit(
        split=split,
        decision_ids=decision_ids,
        artifact_ids=artifact_ids,
        reason="test split reason",
    )


if __name__ == "__main__":
    unittest.main()
