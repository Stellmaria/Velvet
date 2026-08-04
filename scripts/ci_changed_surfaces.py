#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path


FULL_SCAN_EVENTS = frozenset({"schedule", "workflow_dispatch"})
ZERO_SHA = "0" * 40

DOCKER_SHARED_PATTERNS = (
    ".dockerignore",
)

DOCKER_VELVET_PATTERNS = DOCKER_SHARED_PATTERNS + (
    "Dockerfile",
    "requirements.txt",
    "requirements.lock",
    "main.py",
    "velvet_bot/**",
    "scripts/container_healthcheck.py",
)

DOCKER_SUPERVISOR_PATTERNS = DOCKER_SHARED_PATTERNS + (
    "Dockerfile.server-supervisor-proxy",
    "scripts/server_supervisor_proxy.py",
)

DOCKER_VISION_PATTERNS = DOCKER_SHARED_PATTERNS + (
    "Dockerfile.vision-gateway",
    "Dockerfile.vision-runtime",
    "requirements.vision-gateway.txt",
    "vision_gateway/**",
    "scripts/vision_runtime_entrypoint.sh",
    "scripts/vision_model_loader.sh",
)

DOCKER_KRITA_PATTERNS = DOCKER_SHARED_PATTERNS + (
    "Dockerfile.krita-server",
    "docker-compose.server.yml",
    ".env.server.example",
    "deploy/krita-server/**",
    "deploy/server/install-krita-server.sh",
    "deploy/server/krita-smoke.sh",
    "deploy/server/wait-compose-health.sh",
    "tools/krita/**",
    "scripts/krita_server_healthcheck.py",
)

DOCKER_HERMES_PATTERNS = DOCKER_SHARED_PATTERNS + (
    "docker-compose.server.yml",
    ".env.hermes.example",
    ".env.server.example",
    "deploy/hermes-brain/**",
    "deploy/hermes-coders/**",
    "deploy/hermes-entities/**",
    "deploy/hermes-librarian/**",
    "deploy/hermes-operator/**",
    "deploy/hermes-orchestration/**",
)

DOCKER_CI_PATTERNS = (
    ".github/workflows/docker-build.yml",
    ".github/workflows/branch-protection-contract.yml",
    "scripts/ci_changed_surfaces.py",
    "tests/test_ci_changed_surfaces.py",
    "tests/test_docker_build_workflow_contract.py",
)

TEST_DOCS_PATTERNS = (
    "docs/**",
    "*.md",
    "**/*.md",
    "LICENSE",
    "LICENSE.*",
)

TEST_CI_PATTERNS = (
    ".github/workflows/**",
    ".github/actions/**",
    "scripts/ci_*.py",
    "scripts/check_project_notes.py",
    "scripts/security_gate.py",
    "tests/test_ci_*.py",
    "tests/test_*workflow_contract.py",
    "tests/test_security_gate_contract.py",
    "tests/test_project_notes*.py",
)

TEST_HERMES_PATTERNS = (
    ".env.hermes.example",
    "brain-vault/skills/hermes-*/**",
    "deploy/hermes-*/**",
    "tests/test_hermes_*.py",
)

TEST_KRITA_PATTERNS = (
    "Dockerfile.krita-server",
    ".github/workflows/krita-cache-warm.yml",
    "deploy/krita-server/**",
    "deploy/server/install-krita-server.sh",
    "deploy/server/krita-smoke.sh",
    "deploy/server/wait-compose-health.sh",
    "tools/krita/**",
    "scripts/krita_server_healthcheck.py",
    "tests/test_krita_*.py",
)

TEST_FAST_PATH_PATTERNS = (
    TEST_DOCS_PATTERNS
    + TEST_CI_PATTERNS
    + TEST_HERMES_PATTERNS
    + TEST_KRITA_PATTERNS
)

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
    "tests_ci": TEST_CI_PATTERNS,
    "tests_hermes": TEST_HERMES_PATTERNS,
    "tests_krita": TEST_KRITA_PATTERNS,
    "tests_docs_only": TEST_DOCS_PATTERNS,
    "tests_targeted": TEST_CI_PATTERNS + TEST_HERMES_PATTERNS + TEST_KRITA_PATTERNS,
    "tests_full": (),
    "docker_velvet": DOCKER_VELVET_PATTERNS,
    "docker_supervisor": DOCKER_SUPERVISOR_PATTERNS,
    "docker_vision": DOCKER_VISION_PATTERNS,
    "docker_krita": DOCKER_KRITA_PATTERNS,
    "docker_hermes": DOCKER_HERMES_PATTERNS,
    "docker_ci": DOCKER_CI_PATTERNS,
    "docker_any": (
        DOCKER_VELVET_PATTERNS
        + DOCKER_SUPERVISOR_PATTERNS
        + DOCKER_VISION_PATTERNS
        + DOCKER_KRITA_PATTERNS
        + DOCKER_HERMES_PATTERNS
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


def _resolve_pull_request_base(*, base_sha: str, base_ref: str) -> str:
    # GitHub's pull_request payload may retain the base SHA from PR creation
    # while the target branch advances. Prefer the current remote base ref and
    # compute the merge-base against the checked-out PR head.
    if base_ref:
        remote_ref = f"refs/remotes/origin/{base_ref}"
        subprocess.run(
            (
                "git",
                "fetch",
                "--no-tags",
                "origin",
                f"{base_ref}:{remote_ref}",
            ),
            check=True,
        )
        return _git("merge-base", "HEAD", remote_ref).strip()

    if base_sha and base_sha != ZERO_SHA:
        _ensure_commit(base_sha)
        return base_sha
    return ""


def resolve_changed_files(
    *,
    event_name: str,
    base_sha: str,
    before_sha: str,
    base_ref: str = "",
) -> tuple[tuple[str, ...], bool]:
    """Return changed repository paths and whether a conservative full scan is needed."""

    if event_name in FULL_SCAN_EVENTS:
        return tuple(sorted(_git("ls-files").splitlines())), True

    if event_name == "pull_request":
        compare_sha = _resolve_pull_request_base(
            base_sha=base_sha,
            base_ref=base_ref,
        )
    else:
        compare_sha = before_sha
        if compare_sha and compare_sha != ZERO_SHA:
            _ensure_commit(compare_sha)

    if not compare_sha or compare_sha == ZERO_SHA:
        return tuple(sorted(_git("ls-files").splitlines())), True

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

    outputs = {
        name: any(matches_any(path, patterns) for path in paths)
        for name, patterns in SURFACE_PATTERNS.items()
        if name != "tests_full"
    }
    outputs["tests_docs_only"] = bool(paths) and all(
        matches_any(path, TEST_DOCS_PATTERNS) for path in paths
    )
    outputs["tests_full"] = not paths or any(
        not matches_any(path, TEST_FAST_PATH_PATTERNS) for path in paths
    )
    return outputs


def write_outputs(path: Path, outputs: dict[str, bool], *, full_scan: bool) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"full_scan={'true' if full_scan else 'false'}\n")
        for name, enabled in sorted(outputs.items()):
            handle.write(f"{name}={'true' if enabled else 'false'}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--base-ref", default="")
    parser.add_argument("--before-sha", default="")
    parser.add_argument("--github-output", type=Path, required=True)
    parser.add_argument("--changed-files", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths, full_scan = resolve_changed_files(
        event_name=args.event_name,
        base_sha=args.base_sha,
        base_ref=args.base_ref,
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
