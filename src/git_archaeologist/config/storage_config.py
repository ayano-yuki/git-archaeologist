"""Application and storage layout decisions for the MVP."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from enum import StrEnum
import json
from pathlib import Path
from typing import Any


STORAGE_CONFIG_VERSION = "storage-config-v1"
MVP_STORAGE_PROFILE_ID = "mvp-local-storage-v1"
DEFAULT_DATA_ROOT = Path("data") / "local-runtime"


class StorageRole(StrEnum):
    """Storage roles required by the MVP architecture."""

    RAW_ARCHIVE = "raw_archive"
    MANIFEST = "manifest"
    EVENT_STORE = "event_store"
    FULL_TEXT_INDEX = "full_text_index"
    VECTOR_INDEX = "vector_index"
    GRAPH_STORE = "graph_store"
    EVIDENCE_PACKS = "evidence_packs"
    RUN_OUTPUTS = "run_outputs"


@dataclass(frozen=True)
class StorageComponent:
    """One persisted component in the local application stack."""

    role: StorageRole
    backend: str
    path: str
    rebuildable: bool
    git_tracked: bool
    purpose: str


@dataclass(frozen=True)
class ApplicationStack:
    """Fixed MVP application and storage configuration."""

    schema_version: str
    profile_id: str
    application_runtime: str
    data_root: str
    components: tuple[StorageComponent, ...]
    rebuild_command: str
    notes: tuple[str, ...]

    def component(self, role: StorageRole | str) -> StorageComponent:
        storage_role = StorageRole(role)
        for component in self.components:
            if component.role == storage_role:
                return component
        raise KeyError(f"storage component is not configured: {storage_role.value}")


def build_application_stack(data_root: str | Path = DEFAULT_DATA_ROOT) -> ApplicationStack:
    """Return the fixed MVP storage layout."""

    root = Path(data_root).as_posix()
    return ApplicationStack(
        schema_version=STORAGE_CONFIG_VERSION,
        profile_id=MVP_STORAGE_PROFILE_ID,
        application_runtime="Python package with CLI-first local execution through uv.",
        data_root=root,
        components=(
            StorageComponent(
                role=StorageRole.RAW_ARCHIVE,
                backend="content-addressed-json-files",
                path=f"{root}/raw/<repository-id>/<artifact-kind>/<external-id>.json",
                rebuildable=False,
                git_tracked=False,
                purpose="Preserve fetched GitHub and git artifacts before normalization.",
            ),
            StorageComponent(
                role=StorageRole.MANIFEST,
                backend="sqlite",
                path=f"{root}/processed/git-archaeologist.sqlite3",
                rebuildable=True,
                git_tracked=False,
                purpose="Track raw artifact hashes, source URLs, schema versions, and collection state.",
            ),
            StorageComponent(
                role=StorageRole.EVENT_STORE,
                backend="sqlite",
                path=f"{root}/processed/git-archaeologist.sqlite3",
                rebuildable=True,
                git_tracked=False,
                purpose="Store normalized events, observed fields, inferred fields, and schema versions.",
            ),
            StorageComponent(
                role=StorageRole.FULL_TEXT_INDEX,
                backend="sqlite-fts5",
                path=f"{root}/processed/git-archaeologist.sqlite3",
                rebuildable=True,
                git_tracked=False,
                purpose="Provide BM25-style keyword retrieval for identifiers, paths, logs, and exact phrases.",
            ),
            StorageComponent(
                role=StorageRole.VECTOR_INDEX,
                backend="sqlite-compatible-vector-sidecar",
                path=f"{root}/processed/vector-index/",
                rebuildable=True,
                git_tracked=False,
                purpose="Persist embedding vectors with model version and chunk IDs for semantic retrieval.",
            ),
            StorageComponent(
                role=StorageRole.GRAPH_STORE,
                backend="sqlite-edge-tables",
                path=f"{root}/processed/git-archaeologist.sqlite3",
                rebuildable=True,
                git_tracked=False,
                purpose="Store event relationships with relation type, confidence, and supporting evidence.",
            ),
            StorageComponent(
                role=StorageRole.EVIDENCE_PACKS,
                backend="jsonl",
                path=f"{root}/evidence-packs/<query-id>.jsonl",
                rebuildable=True,
                git_tracked=False,
                purpose="Record generated Evidence Packs for reproducible answers and evaluation.",
            ),
            StorageComponent(
                role=StorageRole.RUN_OUTPUTS,
                backend="json-and-markdown",
                path=f"{root}/runs/<run-id>/",
                rebuildable=False,
                git_tracked=False,
                purpose="Store local execution logs, benchmark reports, and evaluation outputs.",
            ),
        ),
        rebuild_command="uv run python -m git_archaeologist.config.storage_config --init",
        notes=(
            "Raw Archive is immutable and not rebuildable unless GitHub or git artifacts are fetched again.",
            "SQLite is the MVP coordination store; vector storage remains sidecar-compatible so the backend can be swapped after benchmark results.",
            "All runtime storage paths are ignored by data/.gitignore unless reviewed data is copied into model-specific sft/ or eval/ folders.",
        ),
    )


def ensure_storage_layout(data_root: str | Path = DEFAULT_DATA_ROOT) -> tuple[Path, ...]:
    """Create the MVP runtime storage directories and return created roots."""

    root = Path(data_root)
    directories = (
        root / "raw",
        root / "processed",
        root / "processed" / "vector-index",
        root / "evidence-packs",
        root / "runs",
    )
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    return directories


def application_stack_to_dict(
    stack: ApplicationStack | None = None,
) -> dict[str, Any]:
    """Return the storage config as a plain dictionary."""

    return asdict(stack or build_application_stack())


def application_stack_to_json(stack: ApplicationStack | None = None) -> str:
    """Return a formatted JSON storage config."""

    return json.dumps(application_stack_to_dict(stack), ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    """Print the storage config and optionally initialize local directories."""

    parser = argparse.ArgumentParser(description="Show or initialize MVP storage layout.")
    parser.add_argument(
        "--data-root",
        default=DEFAULT_DATA_ROOT,
        help="Runtime data root to describe or initialize.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create runtime storage directories before printing the config.",
    )
    args = parser.parse_args(argv)

    if args.init:
        ensure_storage_layout(args.data_root)
    print(application_stack_to_json(build_application_stack(args.data_root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
