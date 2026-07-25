from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from git_archaeologist.runtime_profile import (
    GIB,
    GpuDevice,
    HardwareProfile,
    ModelRole,
    RUNTIME_PROFILE_VERSION,
    _parse_nvidia_smi_csv,
    build_pending_benchmark_report,
    build_runtime_profile_error_report,
    build_runtime_profile,
    check_runtime_constraints,
    load_mvp_model_constraints,
    model_name_to_data_dir_name,
    runtime_profile_error_report_to_dict,
    runtime_profile_to_dict,
    validate_benchmark_report,
    write_benchmark_report,
    write_runtime_profile,
)


class RuntimeProfileTests(unittest.TestCase):
    def test_mvp_constraints_select_three_model_roles(self) -> None:
        constraints = load_mvp_model_constraints()
        by_role = {constraint.role: constraint for constraint in constraints}

        self.assertEqual(
            {ModelRole.EMBEDDING, ModelRole.RERANKER, ModelRole.ANSWER_JUDGE},
            set(by_role),
        )
        self.assertEqual("BAAI/bge-m3", by_role[ModelRole.EMBEDDING].model_id)
        self.assertEqual(
            "BAAI/bge-reranker-v2-m3",
            by_role[ModelRole.RERANKER].model_id,
        )
        self.assertEqual(
            "Qwen/Qwen2.5-Coder-7B-Instruct",
            by_role[ModelRole.ANSWER_JUDGE].model_id,
        )
        self.assertEqual(32768, by_role[ModelRole.ANSWER_JUDGE].max_context_tokens)

    def test_constraint_checks_report_low_vram_without_blocking_cpu_path(self) -> None:
        hardware = HardwareProfile(
            operating_system="test-os",
            machine="x86_64",
            processor="test-cpu",
            python_version="3.12.0",
            logical_cpu_count=8,
            total_ram_bytes=32 * GIB,
            disk_path=".",
            disk_total_bytes=100 * GIB,
            disk_free_bytes=50 * GIB,
            gpu_devices=(),
            notes=(),
        )

        checks = {check.role: check for check in check_runtime_constraints(hardware)}

        self.assertEqual("ready", checks[ModelRole.EMBEDDING].status)
        self.assertEqual("ready", checks[ModelRole.RERANKER].status)
        self.assertEqual("cpu_or_low_vram", checks[ModelRole.ANSWER_JUDGE].status)

    def test_constraint_checks_block_when_ram_is_too_small(self) -> None:
        hardware = HardwareProfile(
            operating_system="test-os",
            machine="x86_64",
            processor="test-cpu",
            python_version="3.12.0",
            logical_cpu_count=4,
            total_ram_bytes=4 * GIB,
            disk_path=".",
            disk_total_bytes=100 * GIB,
            disk_free_bytes=50 * GIB,
            gpu_devices=(GpuDevice("Small GPU", 4 * GIB),),
            notes=(),
        )

        checks = {check.role: check for check in check_runtime_constraints(hardware)}

        self.assertEqual("blocked", checks[ModelRole.EMBEDDING].status)
        self.assertEqual("blocked", checks[ModelRole.RERANKER].status)
        self.assertEqual("blocked", checks[ModelRole.ANSWER_JUDGE].status)

    def test_runtime_profile_is_json_serializable(self) -> None:
        profile = build_runtime_profile(
            captured_at=datetime(2026, 7, 25, tzinfo=timezone.utc)
        )
        payload = runtime_profile_to_dict(profile)
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertEqual(RUNTIME_PROFILE_VERSION, payload["schema_version"])
        self.assertIn("selected_models", payload)
        self.assertIn("constraint_checks", payload)
        self.assertIn("mvp-local-runtime-v1", serialized)

    def test_rejects_naive_capture_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, "captured_at must include a timezone"):
            build_runtime_profile(captured_at=datetime(2026, 7, 25))

    def test_pending_benchmark_report_covers_all_model_roles(self) -> None:
        report = build_pending_benchmark_report(
            measured_at=datetime(2026, 7, 25, tzinfo=timezone.utc)
        )

        self.assertEqual((), validate_benchmark_report(report))
        self.assertEqual(
            {ModelRole.EMBEDDING, ModelRole.RERANKER, ModelRole.ANSWER_JUDGE},
            {result.role for result in report.results},
        )
        self.assertTrue(all(result.status == "pending" for result in report.results))

    def test_rejects_naive_benchmark_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, "measured_at must include a timezone"):
            build_pending_benchmark_report(measured_at=datetime(2026, 7, 25))

    def test_writes_runtime_profile_under_model_runs_directory(self) -> None:
        profile = build_runtime_profile(
            captured_at=datetime(2026, 7, 25, tzinfo=timezone.utc)
        )
        report = build_pending_benchmark_report(
            measured_at=datetime(2026, 7, 25, tzinfo=timezone.utc)
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)

            profile_path = write_runtime_profile(
                profile,
                model_name="Qwen/Qwen2.5-Coder-7B-Instruct",
                data_root=data_root,
            )
            report_path = write_benchmark_report(
                report,
                model_name="Qwen/Qwen2.5-Coder-7B-Instruct",
                data_root=data_root,
            )

            self.assertEqual(
                data_root
                / "Qwen--Qwen2.5-Coder-7B-Instruct"
                / "runs"
                / "runtime-profile"
                / "runtime-profile.json",
                profile_path,
            )
            self.assertTrue(profile_path.is_file())
            self.assertTrue(report_path.is_file())
            self.assertIn(RUNTIME_PROFILE_VERSION, profile_path.read_text(encoding="utf-8"))

    def test_model_name_to_data_dir_name_matches_data_readme(self) -> None:
        self.assertEqual(
            "Qwen--Qwen2.5-Coder-7B-Instruct",
            model_name_to_data_dir_name("Qwen/Qwen2.5-Coder-7B-Instruct"),
        )

        with self.assertRaisesRegex(ValueError, "model_name must not be empty"):
            model_name_to_data_dir_name(" ")

    def test_runtime_profile_error_report_suppresses_secret_fields(self) -> None:
        report = build_runtime_profile_error_report(
            operation="benchmark_answer_judge",
            error_type="model_runtime_unavailable",
            error_message="llama runtime was not installed",
            model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
            retry_count=1,
        )
        payload = runtime_profile_error_report_to_dict(report)

        self.assertEqual("benchmark_answer_judge", payload["operation"])
        self.assertIn("authorization_header", payload["suppressed_fields"])
        self.assertNotIn("raw_token_value", json.dumps(payload))

    def test_parse_nvidia_smi_csv(self) -> None:
        devices = _parse_nvidia_smi_csv(
            "NVIDIA GeForce RTX 4070, 12282\n"
            "NVIDIA A100-SXM4-40GB, 40960\n"
        )

        self.assertEqual("NVIDIA GeForce RTX 4070", devices[0].name)
        self.assertEqual(12282 * 1024 * 1024, devices[0].total_memory_bytes)
        self.assertEqual("NVIDIA A100-SXM4-40GB", devices[1].name)


if __name__ == "__main__":
    unittest.main()
