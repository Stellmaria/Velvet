from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET_BRANCH = "agent/photo-model-input-modes"
GENERATED_PATHS = (
    "docs/package_architecture_inventory.json",
    "docs/package_architecture_inventory.md",
    "docs/package_architecture_exemptions.json",
    "docs/generated/telegram_navigation_inventory.md",
)


def _run(
    *args: str,
    input_text: str | None = None,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )


def _require_ok(result: subprocess.CompletedProcess[str], label: str) -> str:
    output = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode:
        raise AssertionError(f"{label} failed ({result.returncode}):\n{output}")
    return result.stdout.strip()


def _remote_head(branch: str) -> str:
    output = _require_ok(
        _run("git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"),
        "resolve remote branch",
    )
    rows = [line.split() for line in output.splitlines() if line.strip()]
    if len(rows) != 1 or len(rows[0]) != 2:
        raise AssertionError(f"Could not resolve exact remote head for {branch}: {output!r}")
    return rows[0][0].lower()


class Pr484InventoryFinalizeTests(unittest.TestCase):
    def test_regenerate_commit_and_fast_forward_pr_branch(self) -> None:
        if os.environ.get("GITHUB_ACTIONS") != "true":
            self.skipTest("one-shot PR inventory finalizer runs only in GitHub Actions")

        branch = os.environ.get("GITHUB_HEAD_REF", "").strip()
        self.assertEqual(TARGET_BRANCH, branch)
        expected = _remote_head(branch)

        _require_ok(
            _run("git", "cat-file", "-e", f"{expected}^{{commit}}"),
            "validate expected head",
        )
        tree_diff = _run("git", "diff", "--quiet", expected, "HEAD", "--", ".")
        self.assertEqual(
            0,
            tree_diff.returncode,
            "The checked-out pull-request tree differs from its head; refusing to publish generated files.",
        )

        _require_ok(
            _run(
                sys.executable,
                "scripts/inventory_package_architecture.py",
                "--label",
                "p1-package-architecture-baseline",
                "--write",
                "--bootstrap-exemptions",
            ),
            "regenerate package architecture inventory",
        )
        _require_ok(
            _run(
                sys.executable,
                "scripts/telegram_navigation_inventory.py",
                "--root",
                "velvet_bot",
                "--markdown",
                "docs/generated/telegram_navigation_inventory.md",
            ),
            "regenerate Telegram navigation inventory",
        )

        Path(__file__).unlink()
        _require_ok(
            _run(
                "git",
                "add",
                "--",
                *GENERATED_PATHS,
                "tests/test_000_pr484_inventory_capture.py",
            ),
            "stage generated inventory cleanup",
        )
        _require_ok(_run("git", "diff", "--cached", "--check"), "validate staged diff")

        staged = _run("git", "diff", "--cached", "--quiet")
        self.assertEqual(1, staged.returncode, "Expected a non-empty inventory cleanup diff")
        tree = _require_ok(_run("git", "write-tree"), "write cleanup tree")

        commit_env = os.environ.copy()
        commit_env.update(
            {
                "GIT_AUTHOR_NAME": "github-actions[bot]",
                "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
                "GIT_COMMITTER_NAME": "github-actions[bot]",
                "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
            }
        )
        commit = subprocess.run(
            ["git", "commit-tree", tree, "-p", expected],
            cwd=ROOT,
            input="Regenerate inventories after composition merge\n\nRemove the one-shot PR finalizer after publishing exact merged architecture artifacts.\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
            env=commit_env,
        )
        result_sha = _require_ok(commit, "create cleanup commit").lower()
        self.assertRegex(result_sha, r"^[0-9a-f]{40}$")

        latest = _remote_head(branch)
        self.assertEqual(expected, latest, "PR branch moved while inventories were generated")
        _require_ok(
            _run(
                "git",
                "push",
                "origin",
                f"{result_sha}:refs/heads/{branch}",
                timeout=120,
            ),
            "fast-forward cleanup commit",
        )
        print(f"Published inventory cleanup commit {result_sha}")


if __name__ == "__main__":
    unittest.main()
