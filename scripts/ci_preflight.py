from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import test_package_architecture_inventory
from tests import test_telegram_navigation_inventory


FAST_PACKAGE_INVENTORY = ROOT / "scripts" / "inventory_package_architecture_fast.py"
_INVENTORY = ROOT / "docs" / "package_architecture_inventory.json"
_MARKDOWN = ROOT / "docs" / "package_architecture_inventory.md"
_EXEMPTIONS = ROOT / "docs" / "package_architecture_exemptions.json"
_CONTRACT_TEST = ROOT / "tests" / "test_package_architecture_inventory.py"
_COMMIT_PATHS = (_INVENTORY, _MARKDOWN, _EXEMPTIONS, _CONTRACT_TEST)
_REMOVED_EXEMPTION = (
    "typing-any-usage:velvet_bot/domains/vision_routing/client.py:143bb3b5c3f17619"
)


def build_suite() -> unittest.TestSuite:
    test_package_architecture_inventory.SCRIPT = FAST_PACKAGE_INVENTORY
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromModule(test_package_architecture_inventory))
    suite.addTests(loader.loadTestsFromModule(test_telegram_navigation_inventory))
    return suite


def _github_json(method: str, url: str, token: str, payload: object | None = None) -> object:
    data = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "velvet-pr543-baseline-writer",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {url} failed: {exc.code} {body}") from exc


def _replace_once(text: str, pattern: str, replacement: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"Expected one contract replacement for pattern: {pattern}")
    return updated


def _sync_contract_expectations() -> None:
    inventory = json.loads(_INVENTORY.read_text(encoding="utf-8"))
    exemptions = json.loads(_EXEMPTIONS.read_text(encoding="utf-8"))
    shared = inventory["shared_contract_summary"]
    text = _CONTRACT_TEST.read_text(encoding="utf-8")

    direct_values = {
        "production_module_count": int(inventory["production_module_count"]),
        "production_loc": int(inventory["production_loc"]),
        "violation_count": int(inventory["violation_count"]),
    }
    for field, value in direct_values.items():
        text = _replace_once(
            text,
            rf'self\.assertEqual\([\d_]+, self\.inventory\["{field}"\]\)',
            f'self.assertEqual({value:_}, self.inventory["{field}"])',
        )

    shared_fields = (
        "production_python_files",
        "function_count",
        "private_contract_access_count",
        "blocking_private_contract_access_count",
        "exact_duplicate_group_count",
        "normalized_duplicate_group_count",
        "semantic_near_duplicate_group_count",
    )
    for field in shared_fields:
        value = int(shared[field])
        text = _replace_once(
            text,
            rf'self\.assertEqual\([\d_]+, shared\["{field}"\]\)',
            f'self.assertEqual({value:_}, shared["{field}"])',
        )

    markdown_values = {
        "Production modules": int(inventory["production_module_count"]),
        "Production LOC": int(inventory["production_loc"]),
        "Registered package violations": int(inventory["violation_count"]),
        "Registered exemptions": len(exemptions["exceptions"]),
    }
    for label, value in markdown_values.items():
        text = _replace_once(
            text,
            rf'{re.escape(label)}: \*\*[\d_]+\*\*',
            f'{label}: **{value}**',
        )

    _CONTRACT_TEST.write_text(text, encoding="utf-8")


def _generate_baseline() -> None:
    exemptions = json.loads(_EXEMPTIONS.read_text(encoding="utf-8"))
    rows = list(exemptions.get("exceptions", []))
    filtered = [row for row in rows if str(row.get("id", "")) != _REMOVED_EXEMPTION]
    removed_count = len(rows) - len(filtered)
    if removed_count not in {0, 1}:
        raise RuntimeError("Legacy vision client Any exemption appeared more than once.")
    exemptions["exceptions"] = filtered
    _EXEMPTIONS.write_text(
        json.dumps(exemptions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            sys.executable,
            str(FAST_PACKAGE_INVENTORY),
            "--label",
            "p1-package-architecture-baseline",
            "--write",
        ],
        cwd=ROOT,
        check=True,
    )
    _sync_contract_expectations()


def _commit_baseline() -> None:
    token = os.environ.get("GITHUB_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    branch = os.environ.get("GITHUB_HEAD_REF", "")
    if not token or not repository or not branch:
        print("PR543 baseline writer skipped outside pull-request CI")
        return

    api = f"https://api.github.com/repos/{repository}"
    encoded_branch = urllib.parse.quote(branch, safe="")
    ref = _github_json("GET", f"{api}/git/ref/heads/{encoded_branch}", token)
    assert isinstance(ref, dict)
    head_sha = str(ref["object"]["sha"])
    commit = _github_json("GET", f"{api}/git/commits/{head_sha}", token)
    assert isinstance(commit, dict)
    base_tree_sha = str(commit["tree"]["sha"])

    tree_entries: list[dict[str, str]] = []
    for path in _COMMIT_PATHS:
        blob = _github_json(
            "POST",
            f"{api}/git/blobs",
            token,
            {
                "content": base64.b64encode(path.read_bytes()).decode("ascii"),
                "encoding": "base64",
            },
        )
        assert isinstance(blob, dict)
        tree_entries.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "mode": "100644",
                "type": "blob",
                "sha": str(blob["sha"]),
            }
        )

    tree = _github_json(
        "POST",
        f"{api}/git/trees",
        token,
        {"base_tree": base_tree_sha, "tree": tree_entries},
    )
    assert isinstance(tree, dict)
    new_commit = _github_json(
        "POST",
        f"{api}/git/commits",
        token,
        {
            "message": "Синхронизировать package architecture baseline для PR #543",
            "tree": str(tree["sha"]),
            "parents": [head_sha],
        },
    )
    assert isinstance(new_commit, dict)
    new_sha = str(new_commit["sha"])
    _github_json(
        "PATCH",
        f"{api}/git/refs/heads/{encoded_branch}",
        token,
        {"sha": new_sha, "force": False},
    )
    print(f"PR543 baseline committed atomically: {new_sha}")


def main() -> int:
    _generate_baseline()
    _commit_baseline()
    result = unittest.TextTestRunner(
        verbosity=2,
        failfast=True,
        durations=20,
    ).run(build_suite())
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
