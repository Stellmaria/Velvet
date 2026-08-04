from __future__ import annotations

import importlib.util
import stat
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = ROOT / "deploy" / "hermes-coders" / "runtime_source_guard.py"


def _load_guard() -> ModuleType:
    spec = importlib.util.spec_from_file_location("hermes_runtime_source_guard", GUARD_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {GUARD_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GUARD = _load_guard()


class HermesRuntimeSourceGuardTests(unittest.TestCase):
    def test_repair_grants_only_required_world_read_bit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in GUARD.RUNTIME_SOURCES:
                path = root / name
                path.write_text("runtime\n", encoding="utf-8")
                path.chmod(0o600)

            GUARD.ensure_runtime_sources_container_readable(root)
            GUARD.validate_runtime_sources(root)

            for name in GUARD.RUNTIME_SOURCES:
                mode = stat.S_IMODE((root / name).stat().st_mode)
                self.assertEqual(mode, 0o604)

    def test_repair_preserves_existing_owner_execute_bit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in GUARD.RUNTIME_SOURCES:
                path = root / name
                path.write_text("runtime\n", encoding="utf-8")
                path.chmod(0o700)

            GUARD.ensure_runtime_sources_container_readable(root)

            for name in GUARD.RUNTIME_SOURCES:
                mode = stat.S_IMODE((root / name).stat().st_mode)
                self.assertEqual(mode, 0o704)

    def test_missing_runtime_source_still_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(GUARD.RuntimeSourceError):
                GUARD.ensure_runtime_sources_container_readable(root)


if __name__ == "__main__":
    unittest.main()
