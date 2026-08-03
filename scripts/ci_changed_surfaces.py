#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path


FULL_SCAN_EVENTS = frozenset({"schedule", "workflow_dispatch"})
ZERO_SHA = "0" * 40

SURFACE_PATTERNS: dict[str, tuple[str, ...]] = {
    "supply_chain": (
        ".github/workflows/**",
        ".github/security-exceptions.json",
        "requirements.txt",
        "requirements-dev.txt",
        "requirements.lock",
        "requirements-dev.lock",
        "scripts/security_gate.py",
        "tests/test_security_gate_contract.py",
        "scripts/ci_changed_surfaces.py",
        "tests/test_ci_changed_surfaces.py",
    ),
    "static_tools": (
        "*.py",
        "**/*.py",
        "*.sh",
        "**/*.sh",
    ),
    "dependency_audit": (
        "requirements.txt",
        "requirements.lock",
        ".github/security-exceptions.json",
        "tests/fixtures/security/vulnerable-requirements.txt",
    ),
    "codeql_python": (
        "*.py",
        "**/*.py",
    ),
    "codeql_actions": (
        ".github/workflows/**",
        ".github/actions/**",
        "action.yml",
        "action.yaml",
        "**/action.yml",
        "**/action.yaml",
    ),
    "image": (
        "Dockerfile",
        ".dockerignore",
        "requirements.txt",
        "requirements.lock",
        "main.py",
        "velvet_bot/**",
        "scripts/container_healthcheck.py",
        ".github/workflows/security.yml",
        "scripts/ci_changed_surfaces.py",
        "tests/test_ci_changed_surfaces.py",
    ),
    "mypy": (
        "mypy.ini",
        ".github/workflows/type-check.yml",
        "scripts/ci_changed_surfaces.py",
        "tests/test_ci_changed_surfaces.py",
        "requirements-dev.txt",
        "requirements-dev.lock",
        "velvet_bot/core/access/**",
        "velvet_bot/core/config/**",
        "velvet_bot/topics.py",
        "velvet_bot/post_classification.py",
        "velvet_bot/domains/references/models.py",
        "velvet_bot/domains/stories/models.py",
        "velvet_bot/domains/archive/models.py",
        "velvet_bot/domains/archive/preview_models.py",
    ),
}


def _git(*args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout


def _commit_exists(sha: str) -> bool:
    result = subprocess.run(
        ("git", "cat-file", "-e", f"{sha}^{{commit}}"),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _ensure_commit(sha: str) -> None:
    if _commit_exists(sha):
        return
    subprocess.run(
        ("git", "fetch", "--no-tags", "--depth=1", "origin", sha),
        check=True,
    )


def resolve_changed_files(
    *,
    event_name: str,
    base_sha: str,
    before_sha: str,
) -> tuple[tuple[str, ...], bool]:
    """Return changed repository paths and whether a conservative full scan is needed."""

    if event_name in FULL_SCAN_EVENTS:
        return tuple(sorted(_git("ls-files").splitlines())), True

    compare_sha = base_sha if event_name == "pull_request" else before_sha
    if not compare_sha or compare_sha == ZERO_SHA:
        return tuple(sorted(_git("ls-files").splitlines())), True

    _ensure_commit(compare_sha)
    changed = tuple(
        sorted(
            line
            for line in _git("diff", "--name-only", compare_sha, "HEAD").splitlines()
            if line
        )
    )
    return changed, False


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def classify_paths(
    paths: Sequence[str],
    *,
    full_scan: bool = False,
) -> dict[str, bool]:
    if full_scan:
        return {name: True for name in SURFACE_PATTERNS}
    return {
        name: any(matches_any(path, patterns) for path in paths)
        for name, patterns in SURFACE_PATTERNS.items()
    }


def write_outputs(path: Path, outputs: dict[str, bool], *, full_scan: bool) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"full_scan={'true' if full_scan else 'false'}\n")
        for name, enabled in sorted(outputs.items()):
            handle.write(f"{name}={'true' if enabled else 'false'}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--before-sha", default="")
    parser.add_argument("--github-output", type=Path, required=True)
    parser.add_argument("--changed-files", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths, full_scan = resolve_changed_files(
        event_name=args.event_name,
        base_sha=args.base_sha,
        before_sha=args.before_sha,
    )
    if args.changed_files is not None:
        args.changed_files.write_text(
            "".join(f"{path}\n" for path in paths),
            encoding="utf-8",
        )
    outputs = classify_paths(paths, full_scan=full_scan)
    write_outputs(args.github_output, outputs, full_scan=full_scan)

    print("Changed files:")
    for path in paths:
        print(path)
    print("CI surfaces:")
    print(f"full_scan={str(full_scan).lower()}")
    for name, enabled in sorted(outputs.items()):
        print(f"{name}={str(enabled).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
