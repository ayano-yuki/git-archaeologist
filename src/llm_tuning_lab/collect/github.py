from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm_tuning_lab.collect.github_api import GitHubClient
from llm_tuning_lab.collect.github_records import (
    wrap_github_record,
    write_jsonl,
    write_manifest,
)
from llm_tuning_lab.config import load_yaml, override_if_set


def collect_repo(config: dict[str, Any], client: GitHubClient) -> dict[str, Any]:
    repo = config["repo"]
    output_dir = Path(config["output_dir"])
    max_pages = int(config.get("max_pages", 1))
    per_page = int(config.get("per_page", 50))

    params = {
        "state": config.get("state", "all"),
        "sort": config.get("sort", "updated"),
        "direction": config.get("direction", "desc"),
        "since": config.get("since"),
    }
    commit_params = {"since": config.get("since")}

    manifest = {
        "repo": repo,
        "output_dir": str(output_dir),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "counts": {},
    }

    pulls = _collect_endpoint(client, repo, "pull", f"/repos/{repo}/pulls", params, max_pages, per_page)
    issues = _collect_endpoint(client, repo, "issue", f"/repos/{repo}/issues", params, max_pages, per_page)
    commits = _collect_endpoint(
        client,
        repo,
        "commit",
        f"/repos/{repo}/commits",
        commit_params,
        max_pages,
        per_page,
    )

    manifest["counts"]["pulls"] = write_jsonl(output_dir / "pulls.jsonl", pulls)
    manifest["counts"]["issues"] = write_jsonl(output_dir / "issues.jsonl", issues)
    manifest["counts"]["commits"] = write_jsonl(output_dir / "commits.jsonl", commits)

    if config.get("include_pull_details", False):
        detail_records = _collect_pull_details(client, repo, pulls, config)
        manifest["counts"]["pull_details"] = write_jsonl(
            output_dir / "pull_details.jsonl",
            detail_records,
        )

    if config.get("include_pull_commits", False):
        pull_commit_records = _collect_pull_children(
            client,
            repo,
            pulls,
            config,
            per_page,
            kind="pull_commit",
            suffix="commits",
        )
        manifest["counts"]["pull_commits"] = write_jsonl(
            output_dir / "pull_commits.jsonl",
            pull_commit_records,
        )

    if config.get("include_pull_files", False):
        pull_file_records = _collect_pull_children(
            client,
            repo,
            pulls,
            config,
            per_page,
            kind="pull_file",
            suffix="files",
        )
        manifest["counts"]["pull_files"] = write_jsonl(
            output_dir / "pull_files.jsonl",
            pull_file_records,
        )

    if config.get("include_commit_details", False):
        commit_detail_records = _collect_commit_details(client, repo, commits, config)
        manifest["counts"]["commit_details"] = write_jsonl(
            output_dir / "commit_details.jsonl",
            commit_detail_records,
        )

    if config.get("include_check_runs", False):
        check_run_records = _collect_check_runs(client, repo, commits, config)
        manifest["counts"]["check_runs"] = write_jsonl(
            output_dir / "check_runs.jsonl",
            check_run_records,
        )

    if config.get("include_issue_comments", False):
        comments = _collect_endpoint(
            client,
            repo,
            "issue_comment",
            f"/repos/{repo}/issues/comments",
            {"since": config.get("since"), "sort": "updated", "direction": "desc"},
            max_pages,
            per_page,
        )
        manifest["counts"]["issue_comments"] = write_jsonl(output_dir / "issue_comments.jsonl", comments)

    if config.get("include_pull_review_comments", False):
        review_comments = _collect_endpoint(
            client,
            repo,
            "pull_review_comment",
            f"/repos/{repo}/pulls/comments",
            {"since": config.get("since"), "sort": "updated", "direction": "desc"},
            max_pages,
            per_page,
        )
        manifest["counts"]["pull_review_comments"] = write_jsonl(
            output_dir / "pull_review_comments.jsonl",
            review_comments,
        )

    if config.get("include_pull_reviews", False):
        review_records = _collect_pull_reviews(client, repo, pulls, config, per_page)
        manifest["counts"]["pull_reviews"] = write_jsonl(output_dir / "pull_reviews.jsonl", review_records)

    write_manifest(output_dir / "manifest.json", manifest)
    return manifest


def _collect_endpoint(
    client: GitHubClient,
    repo: str,
    kind: str,
    path: str,
    params: dict[str, Any],
    max_pages: int,
    per_page: int,
) -> list[dict[str, Any]]:
    payloads = client.paginate(path, params, max_pages=max_pages, per_page=per_page)
    return [wrap_github_record(repo, kind, payload) for payload in payloads]


def _collect_pull_details(
    client: GitHubClient,
    repo: str,
    pulls: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    if not hasattr(client, "get_json"):
        return []
    max_detail_items = int(config.get("max_detail_items", 25))
    records: list[dict[str, Any]] = []
    for pull in pulls[:max_detail_items]:
        number = pull.get("number")
        if number is None:
            continue
        detail = client.get_json(f"/repos/{repo}/pulls/{number}")
        if isinstance(detail, dict):
            detail["_parent_pull_number"] = number
            records.append(wrap_github_record(repo, "pull_detail", detail))
    return records


def _collect_pull_children(
    client: GitHubClient,
    repo: str,
    pulls: list[dict[str, Any]],
    config: dict[str, Any],
    per_page: int,
    *,
    kind: str,
    suffix: str,
) -> list[dict[str, Any]]:
    max_detail_items = int(config.get("max_detail_items", 25))
    max_pages = int(config.get("max_detail_pages", 1))
    records: list[dict[str, Any]] = []
    for pull in pulls[:max_detail_items]:
        number = pull.get("number")
        if number is None:
            continue
        payloads = client.paginate(
            f"/repos/{repo}/pulls/{number}/{suffix}",
            {},
            max_pages=max_pages,
            per_page=per_page,
        )
        for payload in payloads:
            payload["_parent_pull_number"] = number
            records.append(wrap_github_record(repo, kind, payload))
    return records


def _collect_commit_details(
    client: GitHubClient,
    repo: str,
    commits: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    if not hasattr(client, "get_json"):
        return []
    max_detail_items = int(config.get("max_detail_items", 25))
    records: list[dict[str, Any]] = []
    for commit in commits[:max_detail_items]:
        sha = commit.get("github_id") or commit.get("data", {}).get("sha")
        if not sha:
            continue
        detail = client.get_json(f"/repos/{repo}/commits/{sha}")
        if isinstance(detail, dict):
            records.append(wrap_github_record(repo, "commit_detail", detail))
    return records


def _collect_check_runs(
    client: GitHubClient,
    repo: str,
    commits: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    if not hasattr(client, "get_json"):
        return []
    max_detail_items = int(config.get("max_detail_items", 25))
    records: list[dict[str, Any]] = []
    for commit in commits[:max_detail_items]:
        sha = commit.get("github_id") or commit.get("data", {}).get("sha")
        if not sha:
            continue
        payload = client.get_json(f"/repos/{repo}/commits/{sha}/check-runs")
        check_runs = payload.get("check_runs") if isinstance(payload, dict) else None
        if not isinstance(check_runs, list):
            continue
        for check_run in check_runs:
            check_run["head_sha"] = sha
            records.append(wrap_github_record(repo, "check_run", check_run))
    return records


def _collect_pull_reviews(
    client: GitHubClient,
    repo: str,
    pulls: list[dict[str, Any]],
    config: dict[str, Any],
    per_page: int,
) -> list[dict[str, Any]]:
    max_detail_items = int(config.get("max_detail_items", 25))
    max_pages = int(config.get("max_review_pages", 1))
    records: list[dict[str, Any]] = []

    for pull in pulls[:max_detail_items]:
        number = pull.get("number")
        if number is None:
            continue
        reviews = client.paginate(
            f"/repos/{repo}/pulls/{number}/reviews",
            {},
            max_pages=max_pages,
            per_page=per_page,
        )
        for review in reviews:
            review["_parent_pull_number"] = number
            records.append(wrap_github_record(repo, "pull_review", review))

    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect GitHub repository evidence as JSONL.")
    parser.add_argument("--config", type=Path, default=Path("configs/collect/react_react.yaml"))
    parser.add_argument("--repo", help="Override GitHub owner/name, for example react/react.")
    parser.add_argument("--output-dir", help="Override output directory.")
    parser.add_argument("--max-pages", type=int, help="Override number of pages per endpoint.")
    parser.add_argument("--per-page", type=int, help="Override GitHub API page size.")
    parser.add_argument("--since", help="Only collect records updated after this ISO timestamp.")
    parser.add_argument(
        "--insecure-ssl",
        action="store_true",
        help="Disable TLS verification. Use only when a trusted network proxy breaks validation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_yaml(args.config)
    override_if_set(config, "repo", args.repo)
    override_if_set(config, "output_dir", args.output_dir)
    override_if_set(config, "max_pages", args.max_pages)
    override_if_set(config, "per_page", args.per_page)
    override_if_set(config, "since", args.since)

    client = GitHubClient.from_env()
    if args.insecure_ssl:
        client = GitHubClient(token=client.token, verify_ssl=False)

    manifest = collect_repo(config, client)
    for name, count in manifest["counts"].items():
        print(f"{name}: {count}")
    print(f"manifest: {Path(manifest['output_dir']) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
