from __future__ import annotations

import copy
from datetime import timezone
import json
from pathlib import Path
import tempfile
import unittest

from git_archaeologist.repository_config import (
    ArtifactKind,
    load_builtin_repository_config,
    load_repository_config,
    parse_repository_config,
)


class RepositoryConfigTests(unittest.TestCase):
    def test_loads_react_builtin_repository_config(self) -> None:
        config = load_builtin_repository_config("react/react")

        self.assertEqual(config.repository_id, "react/react")
        self.assertEqual(config.url, "https://github.com/react/react")
        self.assertEqual(config.default_branch, "main")
        self.assertEqual(config.owner, "react")
        self.assertEqual(config.name, "react")

    def test_react_config_defines_reproducible_artifact_ranges(self) -> None:
        config = load_builtin_repository_config()

        self.assertEqual(
            config.enabled_artifact_kinds,
            (
                ArtifactKind.COMMIT,
                ArtifactKind.PULL_REQUEST,
                ArtifactKind.ISSUE,
                ArtifactKind.REVIEW,
                ArtifactKind.REVIEW_COMMENT,
                ArtifactKind.ISSUE_COMMENT,
                ArtifactKind.CI_RUN,
                ArtifactKind.CI_JOB,
            ),
        )
        self.assertEqual(
            config.history_window.since.isoformat(),
            "2024-01-01T00:00:00+00:00",
        )
        self.assertEqual(
            config.history_window.until.isoformat(),
            "2026-07-25T00:00:00+00:00",
        )
        self.assertIs(config.history_window.since.tzinfo, timezone.utc)
        for kind in config.enabled_artifact_kinds:
            scope = config.artifact_scope(kind)
            self.assertEqual(
                scope.effective_history_window(config.history_window),
                config.history_window,
            )

    def test_react_config_defines_exclusions_and_private_info_policy(self) -> None:
        config = load_builtin_repository_config()

        self.assertGreaterEqual(len(config.exclusion_rules), 1)
        self.assertFalse(config.private_info_policy.allow_private_repository)
        self.assertFalse(config.private_info_policy.store_raw_private_data)
        self.assertTrue(config.private_info_policy.redact_secret_like_values)
        self.assertIn("token", config.private_info_policy.redaction_labels)

    def test_react_config_defines_human_error_reporting_payload(self) -> None:
        config = load_builtin_repository_config()

        self.assertTrue(config.error_reporting.notify_human)
        required_fields = set(config.error_reporting.required_fields)
        self.assertGreaterEqual(
            required_fields,
            {
                "repository_id",
                "artifact_kind",
                "target",
                "operation",
                "error_type",
                "error_message",
            },
        )
        self.assertIn("authorization_header", config.error_reporting.suppressed_fields)

    def test_load_repository_config_from_json_file(self) -> None:
        config = load_builtin_repository_config()
        raw_config = {
            "schema_version": config.schema_version,
            "repository": {
                "id": config.repository_id,
                "owner": config.owner,
                "name": config.name,
                "url": config.url,
                "default_branch": config.default_branch,
                "history": {
                    "since": config.history_window.since.isoformat(),
                    "until": config.history_window.until.isoformat(),
                },
            },
            "artifact_scopes": [
                {
                    "kind": scope.kind.value,
                    "enabled": scope.enabled,
                    "selectors": dict(scope.selectors),
                }
                for scope in config.artifact_scopes
            ],
            "exclusion_rules": [
                {
                    "id": rule.rule_id,
                    "artifact_kinds": [
                        artifact_kind.value for artifact_kind in rule.artifact_kinds
                    ],
                    "field": rule.field,
                    "pattern": rule.pattern,
                    "reason": rule.reason,
                }
                for rule in config.exclusion_rules
            ],
            "private_info_policy": {
                "repository_visibility": config.private_info_policy.repository_visibility,
                "allow_private_repository": (
                    config.private_info_policy.allow_private_repository
                ),
                "store_raw_private_data": (
                    config.private_info_policy.store_raw_private_data
                ),
                "redact_secret_like_values": (
                    config.private_info_policy.redact_secret_like_values
                ),
                "redaction_labels": list(config.private_info_policy.redaction_labels),
                "ci_log_policy": config.private_info_policy.ci_log_policy,
            },
            "error_reporting": {
                "notify_human": config.error_reporting.notify_human,
                "required_fields": list(config.error_reporting.required_fields),
                "suppressed_fields": list(config.error_reporting.suppressed_fields),
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "repository.json"
            config_path.write_text(json.dumps(raw_config), encoding="utf-8")

            loaded = load_repository_config(config_path)

        self.assertEqual(loaded.repository_id, config.repository_id)
        self.assertEqual(loaded.enabled_artifact_kinds, config.enabled_artifact_kinds)

    def test_rejects_config_without_required_artifact_scopes(self) -> None:
        raw_config = _raw_builtin_config()
        raw_config["artifact_scopes"] = [
            scope
            for scope in raw_config["artifact_scopes"]
            if scope["kind"] != "ci_run"
        ]

        with self.assertRaisesRegex(ValueError, "required artifact scopes"):
            parse_repository_config(raw_config)

    def test_rejects_open_ended_history_window(self) -> None:
        raw_config = _raw_builtin_config()
        del raw_config["repository"]["history"]["until"]

        with self.assertRaisesRegex(ValueError, "missing required field: until"):
            parse_repository_config(raw_config)

    def test_rejects_mismatched_repository_url(self) -> None:
        raw_config = _raw_builtin_config()
        raw_config["repository"]["url"] = "https://github.com/facebook/react"

        with self.assertRaisesRegex(ValueError, "repository.url path"):
            parse_repository_config(raw_config)


def _raw_builtin_config() -> dict[str, object]:
    config_resource = (
        Path(__file__).parents[1]
        / "src"
        / "git_archaeologist"
        / "config"
        / "repositories"
        / "react_react.json"
    )
    return copy.deepcopy(json.loads(config_resource.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
