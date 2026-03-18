#!/usr/bin/env python3
"""Run user-submitted test cases against FlagOS repositories.

Each test case is a self-contained YAML config that defines:
  - setup: how to install the repo and dependencies (user's perspective)
  - run: how to execute the test (user's perspective)
  - verify: how to check results against gold values

This runner simply executes user-defined commands — it does NOT call
any internal repo test scripts. This keeps test cases at the "user level".

Usage:
    # Run a specific test case
    python tools/run_user_tests.py --case tests/flagscale/train/mixtral/tp2_pp1_ep2.yaml

    # Run all test cases for a repo
    python tools/run_user_tests.py --repo flagscale

    # Run all test cases for a repo+task+model
    python tools/run_user_tests.py --repo flagscale --task train --model mixtral
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Gold-value comparison
# ---------------------------------------------------------------------------

def extract_metrics_from_lines(lines: list[str], metric_keys: list[str]) -> dict:
    """Extract numeric metric values from log lines.

    Supports common log formats:
      - Pipe-separated: "iteration 1/10 | lm loss: 1.161E+01 | ..."
      - Key-value:      "step 1 metric_name:1.234"
    """
    results = {k: [] for k in metric_keys}

    for line in lines:
        for key in metric_keys:
            # Pattern: "key <number>" or "key: <number>"
            # Handle keys with or without trailing colon
            escaped = re.escape(key.rstrip(":"))
            pattern = rf"{escaped}\s*:?\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)"
            match = re.search(pattern, line)
            if match:
                try:
                    results[key].append(float(match.group(1)))
                except ValueError:
                    pass

    return results


def extract_text_from_lines(lines: list[str], pattern: str) -> list[str]:
    """Extract text values from log lines using a regex pattern.

    The pattern must contain at least one capture group. If multiple groups
    are present (e.g. alternation), the first non-None group is used.
    Example pattern: r"output\\.outputs\\[0\\]\\.text=(?:\"(.+?)\"|'(.+?)')"
    """
    results = []
    compiled = re.compile(pattern)

    for line in lines:
        match = compiled.search(line)
        if match:
            # Pick first non-None group
            val = next((g for g in match.groups() if g is not None), None)
            if val is not None:
                results.append(val)

    return results


def compare_gold_values(
    actual: dict, gold: dict, rtol: float = 1e-5, atol: float = 0
) -> tuple[bool, list[str]]:
    """Compare actual metrics against gold values.

    Supports two types of gold entries:
      - numeric (default): {"values": [1.0, 2.0], "type": "numeric"}
      - text:              {"values": ["hello", "world"], "type": "text",
                            "pattern": "regex with (capture group)"}

    Returns (all_passed, list_of_messages).
    """
    messages = []
    all_passed = True

    for key, gold_entry in gold.items():
        gold_values = gold_entry.get("values", [])
        actual_values = actual.get(key, [])
        entry_type = gold_entry.get("type", "numeric")

        if not actual_values:
            messages.append(f"FAIL: No values extracted for metric '{key}'")
            all_passed = False
            continue

        if len(actual_values) != len(gold_values):
            messages.append(
                f"FAIL: Length mismatch for '{key}': "
                f"got {len(actual_values)}, expected {len(gold_values)}"
            )
            all_passed = False
            continue

        if entry_type == "text":
            for i, (a, g) in enumerate(zip(actual_values, gold_values)):
                if a != g:
                    messages.append(
                        f"FAIL: '{key}'[{i}] text mismatch:\n"
                        f"        actual: {a!r}\n"
                        f"        gold:   {g!r}"
                    )
                    all_passed = False
                    break
            else:
                messages.append(f"PASS: '{key}' ({len(gold_values)} text values match)")
        else:
            # numeric comparison — numpy-free allclose
            for i, (a, g) in enumerate(zip(actual_values, gold_values)):
                if abs(a - g) > atol + rtol * abs(g):
                    messages.append(
                        f"FAIL: '{key}'[{i}] mismatch: actual={a}, gold={g}, "
                        f"diff={abs(a-g):.6e}"
                    )
                    all_passed = False
                    break
            else:
                messages.append(f"PASS: '{key}' ({len(gold_values)} values match)")

    return all_passed, messages


# ---------------------------------------------------------------------------
# Test case execution
# ---------------------------------------------------------------------------

def run_commands(cmds: list[str], cwd: str, env: dict | None = None) -> int:
    """Run a list of shell commands sequentially. Return first non-zero exit code."""
    full_env = {**os.environ, **(env or {})}
    for cmd in cmds:
        print(f"  $ {cmd}")
        result = subprocess.run(cmd, shell=True, cwd=cwd, env=full_env)
        if result.returncode != 0:
            print(f"  FAILED (exit code {result.returncode})")
            return result.returncode
    return 0


def run_test_case(case_path: Path, workdir: Path | None = None) -> int:
    """Execute a single user test case.

    Test case YAML format:
        meta:
          repo: flagscale
          task: train
          model: mixtral
          description: "..."

        resources:
          platform: cuda
          device: A100-40GB
          device_count: 1

        setup:
          - pip install flagscale
          - modelscope download --model ... --local_dir ./model_weights

        run:
          - flagscale train mixtral --config ./conf/tp2_pp1_ep2.yaml

        verify:
          log_path: "tests/functional_tests/train/mixtral/test_results/tp2_pp1_ep2/logs/..."
          gold_values_path: "./gold_values/tp2_pp1_ep2.json"
          # OR inline gold values:
          gold_values:
            "lm loss:":
              values: [11.17587, 11.16908, ...]
          rtol: 1e-5
          atol: 0
    """
    print(f"\n{'='*60}")
    print(f"Test Case: {case_path}")
    print(f"{'='*60}")

    with open(case_path) as f:
        config = yaml.safe_load(f)

    meta = config.get("meta", {})
    setup_cmds = config.get("setup", [])
    run_cmds = config.get("run", [])
    verify_config = config.get("verify", {})

    print(f"Repo:  {meta.get('repo', 'unknown')}")
    print(f"Task:  {meta.get('task', 'unknown')}")
    print(f"Model: {meta.get('model', 'unknown')}")
    print(f"Desc:  {meta.get('description', '')}")
    print()

    # Determine working directory — test case files live next to the YAML
    case_dir = case_path.parent.resolve()
    cwd = str(workdir.resolve()) if workdir else str(case_dir)

    env = config.get("env", {})
    # Convert all env values to strings
    env = {k: str(v) for k, v in env.items()}

    # --- Setup ---
    if setup_cmds:
        print("--- Setup ---")
        rc = run_commands(setup_cmds, cwd=cwd, env=env)
        if rc != 0:
            print("SETUP FAILED")
            return rc

    # --- Run ---
    if run_cmds:
        print("\n--- Run ---")
        rc = run_commands(run_cmds, cwd=cwd, env=env)
        if rc != 0:
            print("RUN FAILED")
            return rc

    # --- Verify ---
    if verify_config:
        print("\n--- Verify ---")
        return verify_results(verify_config, case_dir=case_dir, cwd=cwd)

    print("\nPASSED (no verify step)")
    return 0


def verify_results(verify_config: dict, case_dir: Path, cwd: str) -> int:
    """Verify test results against gold values."""
    # Load gold values
    gold = verify_config.get("gold_values")
    if not gold:
        gold_path = verify_config.get("gold_values_path", "")
        if gold_path:
            # Resolve relative to case_dir
            full_path = (case_dir / gold_path) if not Path(gold_path).is_absolute() else Path(gold_path)
            if not full_path.exists():
                # Also try relative to cwd
                full_path = Path(cwd) / gold_path
            if not full_path.exists():
                print(f"FAIL: Gold values file not found: {gold_path}")
                return 1
            with open(full_path) as f:
                gold = json.load(f)
        else:
            print("No gold values defined, skipping verification")
            return 0

    # Extract actual metrics from log
    log_path = verify_config.get("log_path", "")
    if not log_path:
        print("FAIL: verify.log_path is required for gold value comparison")
        return 1

    # Resolve log path — try relative to cwd first, then case_dir
    full_log = Path(cwd) / log_path
    if not full_log.exists():
        full_log = case_dir / log_path
    if not full_log.exists():
        # Try glob pattern (user might use * for timestamp dirs)
        import glob as globmod
        candidates = globmod.glob(str(Path(cwd) / log_path))
        if not candidates:
            candidates = globmod.glob(str(case_dir / log_path))
        if candidates:
            full_log = Path(sorted(candidates)[-1])  # latest match
        else:
            print(f"FAIL: Log file not found: {log_path}")
            return 1

    print(f"Log: {full_log}")

    # Read log via subprocess to bypass NFS client cache
    import time
    time.sleep(2)
    log_content = subprocess.run(
        ["cat", str(full_log)], capture_output=True, text=True
    ).stdout
    log_lines = log_content.splitlines()

    # Separate numeric and text gold entries
    numeric_keys = []
    actual = {}
    for key, entry in gold.items():
        entry_type = entry.get("type", "numeric")
        if entry_type == "text":
            pattern = entry.get("pattern", "")
            if not pattern:
                print(f"FAIL: Text gold entry '{key}' requires a 'pattern' field")
                return 1
            actual[key] = extract_text_from_lines(log_lines, pattern)
        else:
            numeric_keys.append(key)

    if numeric_keys:
        numeric_actual = extract_metrics_from_lines(log_lines, numeric_keys)
        actual.update(numeric_actual)

    rtol = verify_config.get("rtol", 1e-5)
    atol = verify_config.get("atol", 0)
    passed, messages = compare_gold_values(actual, gold, rtol=rtol, atol=atol)

    for msg in messages:
        print(f"  {msg}")

    print(f"\nResult: {'PASSED' if passed else 'FAILED'}")
    return 0 if passed else 1


# ---------------------------------------------------------------------------
# Discovery and batch execution
# ---------------------------------------------------------------------------

def discover_test_cases(
    root: Path, repo: str | None = None,
    task: str | None = None, model: str | None = None
) -> list[Path]:
    """Find all test case YAML files under tests/.

    Test case YAMLs are identified by having a 'meta' key with 'repo'.
    """
    tests_dir = root / "tests"
    cases = []

    for yaml_path in sorted(tests_dir.rglob("*.yaml")):
        # Skip files in sub-config dirs (train/, data.yaml, etc.)
        if yaml_path.name.startswith("_") or yaml_path.name == "data.yaml":
            continue

        try:
            with open(yaml_path) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict) or "meta" not in data:
                continue
            meta = data["meta"]
            if repo and meta.get("repo") != repo:
                continue
            if task and meta.get("task") != task:
                continue
            if model and meta.get("model") != model:
                continue
            cases.append(yaml_path)
        except (yaml.YAMLError, KeyError):
            continue

    return cases


def _load_resource_map(resource_map_path: Path) -> dict:
    """Load resource_map.yaml, returning empty dict on failure."""
    if not resource_map_path.exists():
        return {}
    with open(resource_map_path) as f:
        return yaml.safe_load(f) or {}


def _get_platform_config(resource_map: dict, platform: str) -> dict:
    """Get platform config from resource_map, with fallback to default_platform."""
    platforms = resource_map.get("platforms", {})
    if platform and platform in platforms:
        return platforms[platform]
    default_platform = resource_map.get("default_platform", "")
    if default_platform and default_platform in platforms:
        return platforms[default_platform]
    return {}


def resolve_runner_labels(resources: dict, resource_map_path: Path) -> list[str]:
    """Resolve test case resources to GitHub Actions runner labels.

    Uses platform-based lookup:
      resources.platform -> platforms.<name>.device_labels[resources.device]

    Falls back to platform default_labels, then global default_labels.
    """
    global_default = ["self-hosted"]
    resource_map = _load_resource_map(resource_map_path)
    if not resource_map:
        return global_default

    global_default = resource_map.get("default_labels", global_default)
    platform = resources.get("platform", "")
    pcfg = _get_platform_config(resource_map, platform)
    if not pcfg:
        return global_default

    platform_default = pcfg.get("default_labels", global_default)
    device = resources.get("device", "")
    if not device:
        return platform_default

    # Case-insensitive device lookup
    device_labels = pcfg.get("device_labels", {})
    for key, labels in device_labels.items():
        if key.lower() == device.lower():
            return labels

    return platform_default


def resolve_container_image(
    repo: str, task: str, resources: dict, resource_map_path: Path
) -> str:
    """Resolve test case to a Docker container image.

    Lookup: platform -> container_images -> "<repo>/<task>" | "<repo>" | "default"
    Returns "" if no image is configured.
    """
    resource_map = _load_resource_map(resource_map_path)
    platform = resources.get("platform", "")
    pcfg = _get_platform_config(resource_map, platform)
    images = pcfg.get("container_images", {})
    if not images:
        return ""

    key = f"{repo}/{task}" if task else repo
    image = images.get(key, "")
    if not image and repo:
        image = images.get(repo, "")
    if not image:
        image = images.get("default", "")
    return image


def resolve_container_options(resources: dict, resource_map_path: Path) -> dict:
    """Resolve container runtime options and volumes for the given platform.

    Returns {"container_options": str, "container_volumes": list}.
    """
    resource_map = _load_resource_map(resource_map_path)
    platform = resources.get("platform", "")
    pcfg = _get_platform_config(resource_map, platform)
    return {
        "container_options": pcfg.get("container_options", ""),
        "container_volumes": pcfg.get("container_volumes", []),
    }


def resolve_conda_env(
    repo: str, task: str, resources: dict, resource_map_path: Path
) -> str:
    """Resolve conda environment name for the given platform and repo/task.

    Lookup: platform -> conda_env -> "<repo>/<task>" | "<repo>" | "default"
    Returns "" if no conda env is configured.
    """
    resource_map = _load_resource_map(resource_map_path)
    platform = resources.get("platform", "")
    pcfg = _get_platform_config(resource_map, platform)
    conda_envs = pcfg.get("conda_env", {})
    if not conda_envs:
        return ""

    key = f"{repo}/{task}" if task else repo
    env = conda_envs.get(key, "")
    if not env and repo:
        env = conda_envs.get(repo, "")
    if not env:
        env = conda_envs.get("default", "")
    return env


def list_test_resources(
    root: Path, repo: str | None = None,
    task: str | None = None, model: str | None = None
) -> list[dict]:
    """List test cases with their resource requirements, runner labels, and container config.

    Returns a list of dicts with keys:
      case_path, resources, runner_labels, container_image, container_init,
      container_options, container_volumes
    """
    cases = discover_test_cases(root, repo, task, model)
    resource_map_path = root / "resource_map.yaml"
    result = []

    for case_path in cases:
        with open(case_path) as f:
            data = yaml.safe_load(f)
        meta = data.get("meta", {})
        resources = data.get("resources", {})
        runner_labels = resolve_runner_labels(resources, resource_map_path)
        container_image = resolve_container_image(
            meta.get("repo", ""), meta.get("task", ""), resources, resource_map_path
        )
        conda_env = resolve_conda_env(
            meta.get("repo", ""), meta.get("task", ""), resources, resource_map_path
        )
        container_opts = resolve_container_options(resources, resource_map_path)
        result.append({
            "case_path": str(case_path),
            "resources": resources,
            "runner_labels": runner_labels,
            "container_image": container_image,
            "conda_env": conda_env,
            **container_opts,
        })

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run user-submitted FlagOS test cases"
    )
    parser.add_argument("--case", help="Path to a specific test case YAML")
    parser.add_argument("--repo", help="Run all cases for this repo")
    parser.add_argument("--task", help="Filter by task type")
    parser.add_argument("--model", help="Filter by model name")
    parser.add_argument(
        "--workdir",
        help="Working directory for command execution (default: test case directory)"
    )
    parser.add_argument(
        "--list-resources", action="store_true",
        help="List test cases with resource requirements and runner labels (JSON output)"
    )
    args = parser.parse_args()

    # --list-resources mode: output JSON and exit
    if args.list_resources:
        root = Path(".")
        result = list_test_resources(root, args.repo, args.task, args.model)
        print(json.dumps(result, indent=2))
        sys.exit(0)

    workdir = Path(args.workdir) if args.workdir else None

    if args.case:
        case_path = Path(args.case)
        if not case_path.exists():
            print(f"ERROR: Test case not found: {case_path}")
            sys.exit(1)
        sys.exit(run_test_case(case_path, workdir))

    if not args.repo:
        print("ERROR: Specify --case, --repo, or --list-resources")
        sys.exit(1)

    root = Path(".")
    cases = discover_test_cases(root, args.repo, args.task, args.model)

    if not cases:
        print(f"No test cases found for repo={args.repo} task={args.task} model={args.model}")
        sys.exit(0)

    print(f"Found {len(cases)} test case(s)")
    failed = 0
    for case in cases:
        rc = run_test_case(case, workdir)
        if rc != 0:
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {len(cases) - failed}/{len(cases)} passed")
    print(f"{'='*60}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
