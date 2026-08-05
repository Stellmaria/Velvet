from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from velvet_bot.app import workers
from velvet_bot.domains.media_generation.friendly_worker import (
    FriendlyKieGenerationWorker,
)

ROOT = Path(__file__).resolve().parents[1]


class KieWorkerBootstrapContractTests(unittest.TestCase):
    def test_app_workers_exports_canonical_friendly_worker(self) -> None:
        self.assertIs(workers.KieGenerationWorker, FriendlyKieGenerationWorker)
        self.assertTrue(
            callable(workers.KieGenerationWorker.install_delivery_handler)
        )

    def test_feature_installers_execute_in_declared_order(self) -> None:
        script = """
from velvet_bot.app.composition import build_application_composition

composition = build_application_composition()
stages = composition.feature_stages_factory()
assert tuple(stage.name for stage in stages) == composition.feature_stage_names
for stage in stages:
    stage.install()
"""
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(
            0,
            completed.returncode,
            msg=(
                "Feature installer smoke failed.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
