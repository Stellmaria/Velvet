from __future__ import annotations

import importlib.util
import json
import re
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def install_stubs() -> None:
    base = types.ModuleType("codex_runner")
    base.Handler = object
    base.ThreadingHTTPServer = object
    base._RETRYABLE_MODEL_ERRORS = re.compile(
        r"(?i)(rate.?limit|capacity|unavailable|429)"
    )
    base.fallback_order = lambda selected, allowed: tuple(
        [selected] + [item for item in allowed if item != selected]
    )
    base.parse_jsonl_output = lambda stdout: (stdout, None, None)
    base.parse_structured_output = lambda output: {"status": "completed"}
    base.redact_text = lambda value: value
    base.render_legacy_output = lambda payload: "STATUS: completed"
    base.utc_now = lambda: "2026-08-03T00:00:00+00:00"

    class FakeRouted:
        def __init__(self):
            self.codex_bin = "codex"
            self.codex_home = Path("/tmp/codex")
            self.output_schema = Path("/tmp/codex/output.schema.json")
            self.workspace = Path("/tmp/workspace")
            self.allowed_models = (
                "gpt-5.6-luna",
                "gpt-5.6-terra",
                "gpt-5.6-sol",
            )
            self.default_model = "gpt-5.6-terra"
            self.timeout_seconds = 60
            self._process_lock = __import__("threading").RLock()
            self._processes = {}
            self._execution_lock = __import__("threading").Lock()

        def capabilities(self):
            return {"routing": {"default": self.default_model}}

    routed = types.ModuleType("codex_routed_runner")
    routed.RoutedCodexManager = FakeRouted
    sys.modules["codex_runner"] = base
    sys.modules["codex_routed_runner"] = routed


class CodexFirstPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_stubs()
        cls.module = load_module(
            "codex_first_runner",
            ROOT / "deploy/hermes-coders/codex_first_runner.py",
        )
        cls.safe_module = load_module(
            "codex_first_safe_runner_test_module",
            ROOT / "deploy/hermes-coders/codex_first_safe_runner.py",
        )

    def test_fallback_reason_is_infrastructure_only(self) -> None:
        self.assertEqual(
            "subscription_limit",
            self.module.provider_fallback_reason(
                "You have reached your agentic usage limit"
            ),
        )
        self.assertEqual(
            "subscription_auth",
            self.module.provider_fallback_reason("device auth expired"),
        )
        self.assertEqual(
            "codex_capacity",
            self.module.provider_fallback_reason("model temporarily unavailable"),
        )
        self.assertIsNone(
            self.module.provider_fallback_reason(
                "pytest failed: assertion mismatch in test_balance"
            )
        )

    def test_provider_home_filters_secrets_but_keeps_github(self) -> None:
        source = (
            ROOT / "deploy/hermes-coders/codex_first_runner.py"
        ).read_text(encoding="utf-8")
        for secret in (
            "API_SERVER_KEY",
            "BYESU_HERMES_CODEX_API_KEY",
            "CODEX_RUNNER_API_KEY",
            "DATABASE_URL",
            "TELEGRAM_BOT_TOKEN",
        ):
            self.assertIn(f'"{secret}"', source)
        self.assertNotIn('"GH_TOKEN"', source)

    def test_fingerprint_covers_head_refs_and_worktree(self) -> None:
        source = (
            ROOT / "deploy/hermes-coders/codex_first_runner.py"
        ).read_text(encoding="utf-8")
        for marker in (
            '"rev-parse", "HEAD"',
            '"rev-parse", "--abbrev-ref", "HEAD"',
            '"for-each-ref"',
            '"status"',
            '"--untracked-files=all"',
        ):
            self.assertIn(marker, source)
        mutation_guard = "mutated = self._fingerprint() != baseline"
        self.assertGreaterEqual(source.count(mutation_guard), 3)
        self.assertLess(
            source.index(mutation_guard),
            source.index('if candidate in {"subscription_limit", "subscription_auth"}'),
        )

    def test_lifecycle_jsonl_does_not_block_provider_fallback(self) -> None:
        stdout = "\n".join(
            (
                json.dumps({"type": "thread.started", "thread_id": "abc"}),
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "working"},
                    }
                ),
            )
        )
        self.assertFalse(self.safe_module.primary_execution_started(stdout))

    def test_tool_and_file_events_block_automatic_retry(self) -> None:
        for item_type in (
            "command_execution",
            "file_change",
            "mcp_tool_call",
            "collab_tool_call",
            "custom_execution",
        ):
            with self.subTest(item_type=item_type):
                stdout = json.dumps(
                    {
                        "type": "item.started",
                        "item": {"type": item_type},
                    }
                )
                self.assertTrue(
                    self.safe_module.primary_execution_started(stdout)
                )

    def test_safe_wrapper_records_fail_closed_route_state(self) -> None:
        source = (
            ROOT / "deploy/hermes-coders/codex_first_safe_runner.py"
        ).read_text(encoding="utf-8")
        self.assertIn("primary_output_started=True", source)
        self.assertIn('"automatic_retry": False', source)
        self.assertIn(
            "Provider fallback blocked after primary execution events.",
            source,
        )
        self.assertIn(
            "mutation_started=super()._fingerprint() != baseline",
            source,
        )


class DirectCoderContractTests(unittest.TestCase):
    def test_runtime_override_wires_both_projects(self) -> None:
        source = (
            ROOT / "deploy/hermes-coders/compose.runtime.yaml"
        ).read_text(encoding="utf-8")
        self.assertEqual(2, source.count("/app/codex_first_runner.py"))
        self.assertEqual(2, source.count("/app/codex_first_safe_runner.py"))
        self.assertEqual(2, source.count("/app/codex_delegate.py"))
        self.assertIn(
            "HERMES_CODEX_DELEGATE_URL: http://hermes-coder-velvet:8642",
            source,
        )
        self.assertIn(
            "HERMES_CODEX_DELEGATE_URL: http://hermes-coder-max:8642",
            source,
        )
        self.assertEqual(
            2,
            source.count('CODEX_PROVIDER_FALLBACK_ENABLED: "true"'),
        )

    def test_brain_skill_is_only_on_coder_entities(self) -> None:
        manifest = json.loads(
            (ROOT / "brain-vault/manifest.json").read_text(encoding="utf-8")
        )
        skill = "brain-vault/skills/codex-first/SKILL.md"
        self.assertIn(skill, manifest["entities"]["velvet-coder"]["skills"])
        self.assertIn(skill, manifest["entities"]["max-coder"]["skills"])
        self.assertNotIn(skill, manifest["entities"]["kael"]["skills"])
        self.assertNotIn(skill, manifest["entities"]["velvet-librarian"]["skills"])


if __name__ == "__main__":
    unittest.main()
