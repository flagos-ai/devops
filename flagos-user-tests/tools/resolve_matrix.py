#!/usr/bin/env python3
"""Resolve test case resources into a GitHub Actions matrix.

Reads detection outputs (changed_cases / changed_repos / changed_repos_list)
and produces a JSON matrix with runner_labels, container_image, container_options,
and container_volumes per test case entry.

Usage (from workflow):
    python tools/resolve_matrix.py \
      --changed-cases '${{ steps.detect.outputs.changed_cases }}' \
      --changed-repos '${{ steps.detect.outputs.changed_repos }}' \
      --changed-repos-list '${{ steps.detect.outputs.changed_repos_list }}'
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_user_tests import (
    list_test_resources,
    resolve_conda_env,
    resolve_container_image,
    resolve_container_options,
    resolve_runner_labels,
)

import yaml


def make_entry(case_path: str, meta: dict, resources: dict, resource_map_path: Path) -> dict:
    """Build a matrix entry with runner labels and per-platform container config."""
    labels = resolve_runner_labels(resources, resource_map_path)
    image = resolve_container_image(
        meta.get("repo", ""), meta.get("task", ""),
        resources, resource_map_path,
    )
    init_cmd = resolve_conda_env(
        meta.get("repo", ""), meta.get("task", ""),
        resources, resource_map_path,
    )
    opts = resolve_container_options(resources, resource_map_path)
    return {
        "case_path": case_path,
        "repo": meta.get("repo", ""),
        "task": meta.get("task", ""),
        "model": meta.get("model", ""),
        "runner_labels": json.dumps(labels),
        "container_image": image,
        "conda_env": init_cmd,
        "container_options": opts["container_options"],
        "container_volumes": json.dumps(opts["container_volumes"]),
    }


def make_empty_entry(**kwargs) -> dict:
    """Build a placeholder entry with defaults."""
    return {
        "case_path": "", "repo": "", "task": "", "model": "",
        "runner_labels": json.dumps(["self-hosted"]),
        "container_image": "", "conda_env": "",
        "container_options": "",
        "container_volumes": json.dumps([]),
        **kwargs,
    }


def resource_entry_to_matrix(entry: dict, repo: str = "", task: str = "", model: str = "") -> dict:
    """Convert a list_test_resources entry to a matrix entry."""
    return {
        "case_path": entry["case_path"],
        "repo": repo or "", "task": task or "", "model": model or "",
        "runner_labels": json.dumps(entry["runner_labels"]),
        "container_image": entry.get("container_image", ""),
        "conda_env": entry.get("conda_env", ""),
        "container_options": entry.get("container_options", ""),
        "container_volumes": json.dumps(entry.get("container_volumes", [])),
    }


def main():
    parser = argparse.ArgumentParser(description="Resolve test resources to CI matrix")
    parser.add_argument("--changed-cases", default="")
    parser.add_argument("--changed-repos", default="")
    parser.add_argument("--changed-repos-list", default="")
    parser.add_argument("--root", default=".", help="Root directory of flagos-user-tests")
    args = parser.parse_args()

    root = Path(args.root)
    resource_map_path = root / "resource_map.yaml"
    matrix_entries = []

    if args.changed_cases:
        cases = json.loads(args.changed_cases)
        for case_path in cases:
            p = root / case_path if not Path(case_path).is_absolute() else Path(case_path)
            if p.exists():
                data = yaml.safe_load(p.read_text())
                matrix_entries.append(make_entry(
                    case_path, data.get("meta", {}),
                    data.get("resources", {}), resource_map_path,
                ))

    elif args.changed_repos_list:
        repos = json.loads(args.changed_repos_list)
        for repo in repos:
            for entry in list_test_resources(root, repo=repo):
                matrix_entries.append(resource_entry_to_matrix(entry, repo=repo))

    elif args.changed_repos:
        info = json.loads(args.changed_repos)
        if info.get("repo") == "_none_":
            matrix_entries.append(make_empty_entry(repo="_none_"))
        else:
            repo = info["repo"]
            task = info.get("task", "") or None
            model = info.get("model", "") or None
            entries = list_test_resources(root, repo=repo, task=task, model=model)
            if entries:
                for entry in entries:
                    matrix_entries.append(resource_entry_to_matrix(
                        entry, repo=repo,
                        task=info.get("task", ""),
                        model=info.get("model", ""),
                    ))
            else:
                matrix_entries.append(make_empty_entry(repo=repo))

    matrix = {"include": matrix_entries}
    matrix_json = json.dumps(matrix)
    print(f"Matrix: {matrix_json}")

    # Write to GITHUB_OUTPUT if available
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"matrix={matrix_json}\n")
    else:
        # For local testing, just print to stdout
        print(json.dumps(matrix, indent=2))


if __name__ == "__main__":
    main()
