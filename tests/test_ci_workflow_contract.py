from __future__ import annotations

import importlib.util
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
SHARD_SCRIPT = ROOT / "scripts" / "ci_test_shard.py"
PREFLIGHT_SCRIPT = ROOT / "scripts" / "ci_preflight.py"


class CiWorkflowContractTests(unittest.TestCase):
    def test_workflow_cancels_obsolete_runs(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("concurrency:", source)
        self.assertIn("cancel-in-progress: true", source)
        self.assertIn("github.event.pull_request.number || github.ref", source)

    def test_workflow_runs_four_parallel_database_shards(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("CI_TEST_SHARDS: \"4\"", source)
        self.assertIn("shard: [0, 1, 2, 3]", source)
        self.assertIn("name: test-shard-${{ matrix.shard }}", source)
        self.assertIn("sudo systemctl start postgresql.service", source)
        self.assertIn("CREATE ROLE velvet LOGIN SUPERUSER", source)
        self.assertIn("CREATE DATABASE velvet_test OWNER velvet", source)
        self.assertNotIn("image: postgres:16", source)
        self.assertNotIn("services:\n      postgres:", source)
        self.assertIn("fail-fast: true", source)

    def test_preflight_and_required_status_are_preserved(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        preflight = PREFLIGHT_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("name: preflight", source)
        self.assertIn("python scripts/ci_preflight.py", source)
        self.assertIn("test_package_architecture_inventory", preflight)
        self.assertIn("test_telegram_navigation_inventory", preflight)
        self.assertIn("inventory_package_architecture_fast.py", preflight)
        self.assertIn("name: unit-tests", source)
        self.assertIn("SHARDS_RESULT: ${{ needs.test-shards.result }}", source)

    def test_dependency_install_and_failure_logs_stay_lean(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("pip install --upgrade pip", source)
        self.assertNotIn("cache: pip", source)
        self.assertIn("astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b", source)
        self.assertIn('version: "0.11.16"', source)
        self.assertIn("cache-dependency-glob: requirements.txt", source)
        self.assertIn("uv pip install --system -r requirements.txt", source)
        self.assertGreaterEqual(source.count("if: failure()"), 2)
        self.assertNotIn("if: always()\n        uses: actions/upload-artifact", source)

    def test_shard_partition_covers_every_parallel_test_once(self) -> None:
        spec = importlib.util.spec_from_file_location("ci_test_shard", SHARD_SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec is not None else None)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        files = module.discover_test_files()
        partitions = module.partition_test_files(files, total=4)
        assigned = [path for partition in partitions for path in partition]

        self.assertTrue(files)
        self.assertTrue(all(partition for partition in partitions))
        self.assertEqual(Counter(files), Counter(assigned))
        self.assertTrue(module.PREFLIGHT_TESTS.isdisjoint(files))


if __name__ == "__main__":
    unittest.main()
