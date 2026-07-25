from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from git_archaeologist.storage_config import (
    DEFAULT_DATA_ROOT,
    STORAGE_CONFIG_VERSION,
    StorageRole,
    application_stack_to_dict,
    build_application_stack,
    ensure_storage_layout,
    main,
)


class StorageConfigTests(unittest.TestCase):
    def test_storage_stack_defines_required_components(self) -> None:
        stack = build_application_stack()
        roles = {component.role for component in stack.components}

        self.assertEqual(
            {
                StorageRole.RAW_ARCHIVE,
                StorageRole.MANIFEST,
                StorageRole.EVENT_STORE,
                StorageRole.FULL_TEXT_INDEX,
                StorageRole.VECTOR_INDEX,
                StorageRole.GRAPH_STORE,
                StorageRole.EVIDENCE_PACKS,
                StorageRole.RUN_OUTPUTS,
            },
            roles,
        )
        self.assertEqual(STORAGE_CONFIG_VERSION, stack.schema_version)
        self.assertEqual(DEFAULT_DATA_ROOT.as_posix(), stack.data_root)

    def test_runtime_storage_is_not_git_tracked(self) -> None:
        stack = build_application_stack()

        self.assertTrue(all(not component.git_tracked for component in stack.components))
        self.assertFalse(stack.component(StorageRole.RAW_ARCHIVE).rebuildable)
        self.assertTrue(stack.component(StorageRole.FULL_TEXT_INDEX).rebuildable)
        self.assertIn("sqlite", stack.component(StorageRole.EVENT_STORE).backend)
        self.assertIn("fts5", stack.component(StorageRole.FULL_TEXT_INDEX).backend)

    def test_custom_data_root_is_applied_to_component_paths(self) -> None:
        stack = build_application_stack("data/test-runtime")

        self.assertEqual("data/test-runtime", stack.data_root)
        for component in stack.components:
            self.assertTrue(component.path.startswith("data/test-runtime/"))

    def test_ensure_storage_layout_creates_rebuildable_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runtime"

            directories = ensure_storage_layout(root)

            self.assertEqual(
                {
                    root / "raw",
                    root / "processed",
                    root / "processed" / "vector-index",
                    root / "evidence-packs",
                    root / "runs",
                },
                set(directories),
            )
            self.assertTrue(all(directory.is_dir() for directory in directories))

    def test_storage_stack_is_json_serializable(self) -> None:
        payload = application_stack_to_dict()
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertIn(STORAGE_CONFIG_VERSION, serialized)
        self.assertIn("sqlite-fts5", serialized)
        self.assertIn("vector-index", serialized)

    def test_main_init_creates_custom_data_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runtime"
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--init", "--data-root", str(root)])

            self.assertEqual(0, exit_code)
            self.assertIn("storage-config-v1", stdout.getvalue())
            self.assertTrue((root / "raw").is_dir())
            self.assertTrue((root / "processed" / "vector-index").is_dir())


if __name__ == "__main__":
    unittest.main()
