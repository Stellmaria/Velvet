from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


router_mod = load_module(
    "coder_router",
    ROOT / "deploy/hermes-operator/coder_router.py",
)
tier_router = load_module(
    "hermes_tier_read_only_test_module",
    ROOT / "deploy/hermes-operator/tier_router.py",
)


class TierReadOnlyContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(
            os.environ,
            {
                "HERMES_CODER_ROUTER_CLIENT_TOKEN": "c" * 48,
                "HERMES_CODER_VELVET_TOKEN": "v" * 48,
                "HERMES_CODER_MAX_TOKEN": "m" * 48,
                "HERMES_CODER_VELVET_GITHUB_TOKEN": "g" * 48,
                "HERMES_CODER_MAX_GITHUB_TOKEN": "h" * 48,
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.routing = {
            "task_type": "read_only",
            "complexity": "small",
            "risk": "low",
            "mutation_policy": "read_only",
            "requested_tier": "small",
        }

    def test_read_only_handoff_forbids_file_and_git_mutation(self) -> None:
        target = router_mod.load_targets()["velvet"]
        handoff = tier_router.build_tier_handoff(
            target,
            task_id="a" * 32,
            task="Проверь статус и подготовь сводку без изменений",
            source="owner-request",
            routing=self.routing,
        )
        self.assertNotIn("read and edit files inside /workspace", handoff["allowed_actions"])
        self.assertNotIn(
            "create one branch, commit, push and pull request",
            handoff["allowed_actions"],
        )
        self.assertIn(
            "file or Git mutation, branch, commit, push or pull request",
            handoff["forbidden_actions"],
        )
        prompt = tier_router.build_tier_prompt(
            target,
            task_id="a" * 32,
            task="Проверь статус и подготовь сводку без изменений",
            source="owner-request",
            routing=self.routing,
        )
        self.assertIn("только read-only анализ без branch/commit/PR", prompt)
        self.assertNotIn("создай одну ветку", prompt)

    def test_read_only_submit_sends_non_mutating_instruction(self) -> None:
        router = tier_router.TierAwareCoderRouter()
        with patch.object(
            router,
            "upstream",
            return_value={
                "run_id": "run_read_only",
                "status": "queued",
                "selected_primary_model": "gpt-5.6-luna",
            },
        ) as upstream:
            result = router.submit(
                "velvet",
                {
                    "task_id": "b" * 32,
                    "task": "Проверь статус без изменений",
                    "source": "owner-request",
                    **self.routing,
                },
            )
        forwarded = upstream.call_args.args[3]
        self.assertIn("не меняй workspace", forwarded["instructions"])
        self.assertIn("не создавай branch/commit/PR", forwarded["instructions"])
        self.assertEqual("read_only", forwarded["mutation_policy"])
        self.assertEqual("small", result["requested_tier"])


if __name__ == "__main__":
    unittest.main()
