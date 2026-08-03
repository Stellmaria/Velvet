from __future__ import annotations

import importlib.util
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
SHARD_SCRIPT = ROOT / "scripts" / "ci_test_shard.py"
DURATION_HINTS = ROOT / "scripts" / "ci_test_durations.json"
PREFLIGHT_SCRIPT = ROOT / "scripts" / "ci_preflight.py"


def load_shard_module():
    spec = importlib.util.spec_from_file_location("ci_test_shard", SHARD_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load CI shard script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CiWorkflowContractTests(unittest.TestCase):
    def test_workflow_cancels_obsolete_runs(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("concurrency:", source)
        self.assertIn("cancel-in-progress: true", source)
        self.assertIn("github.event.pull_request.number || github.ref", source)

    def test_workflow_runs_four_parallel_database_shards(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('CI_TEST_SHARDS: "4"', source)
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
        self.assertIn("astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9", source)
        self.assertIn('version: "0.11.16"', source)
        self.assertIn("cache-dependency-glob: requirements.lock", source)
        self.assertIn(
            "uv pip install --system --require-hashes -r requirements.lock",
            source,
        )
        self.assertGreaterEqual(source.count("if: failure()"), 2)
        self.assertNotIn("if: always()\n        uses: actions/upload-artifact", source)

    def test_shard_partition_covers_every_parallel_test_once(self) -> None:
        module = load_shard_module()
        files = module.discover_test_files()
        hints = module.load_duration_hints()
        partitions = module.partition_test_files(
            files,
            total=4,
            duration_hints=hints,
        )
        assigned = [path for partition in partitions for path in partition]

        self.assertTrue(files)
        self.assertTrue(all(partition for partition in partitions))
        self.assertEqual(Counter(files), Counter(assigned))
        self.assertTrue(module.PREFLIGHT_TESTS.isdisjoint(files))

    def test_duration_hints_are_current_positive_test_files(self) -> None:
        module = load_shard_module()
        files = set(module.discover_test_files())
        hints = module.load_duration_hints(DURATION_HINTS)

        self.assertTrue(hints)
        self.assertFalse(set(hints) - files)
        self.assertTrue(all(seconds > 0 for seconds in hints.values()))

    def test_four_heaviest_measured_files_land_on_distinct_shards(self) -> None:
        module = load_shard_module()
        hints = module.load_duration_hints()
        partitions = module.partition_test_files(
            module.discover_test_files(),
            total=4,
            duration_hints=hints,
        )
        shard_by_file = {
            path: index
            for index, partition in enumerate(partitions)
            for path in partition
        }
        heaviest = sorted(
            hints,
            key=lambda path: (-hints[path], path.as_posix()),
        )[:4]

        self.assertEqual(4, len(heaviest))
        self.assertEqual(4, len({shard_by_file[path] for path in heaviest}))


if __name__ == "__main__":
    unittest.main()
