from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BRAIN_RUNTIME = ROOT / "deploy" / "hermes-brain"
sys.path.insert(0, str(BRAIN_RUNTIME))

import context_compiler as compiler  # noqa: E402
import install_context_pack as installer  # noqa: E402
import verify_installed_context as runtime_verifier  # noqa: E402

LIBRARIAN_SPEC = importlib.util.spec_from_file_location(
    "brain_vault_librarian_profile",
    ROOT / "deploy/hermes-librarian/prepare_profile.py",
)
assert LIBRARIAN_SPEC and LIBRARIAN_SPEC.loader
librarian_profile = importlib.util.module_from_spec(LIBRARIAN_SPEC)
yaml_stub = types.ModuleType("yaml")
yaml_stub.YAMLError = ValueError
yaml_stub.safe_load = json.loads
yaml_stub.safe_dump = lambda value, **_kwargs: json.dumps(  # noqa: E731
    value,
    ensure_ascii=False,
    indent=2,
) + "\n"
with patch.dict(sys.modules, {"yaml": yaml_stub}):
    LIBRARIAN_SPEC.loader.exec_module(librarian_profile)


class BrainVaultCompilerTests(unittest.TestCase):
    def compile(self, entity: str, root: Path) -> Path:
        output = root / entity
        compiler.compile_entity(ROOT, entity, output)
        return output

    def test_vault_and_four_canonical_entities_validate(self) -> None:
        checked = compiler.validate_vault(ROOT)
        manifest = compiler.load_manifest(ROOT)
        self.assertEqual(
            {"kael", "velvet-coder", "max-coder", "velvet-librarian"},
            set(manifest["entities"]),
        )
        self.assertIn("brain-vault/Home.md", checked)
        self.assertIn("brain-vault/schemas/codex-task-output.schema.json", checked)

    def test_compile_is_byte_deterministic_and_hash_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.compile("kael", root / "first")
            second = self.compile("kael", root / "second")
            first_files = {
                path.relative_to(first).as_posix(): path.read_bytes()
                for path in first.rglob("*")
                if path.is_file()
            }
            second_files = {
                path.relative_to(second).as_posix(): path.read_bytes()
                for path in second.rglob("*")
                if path.is_file()
            }
            self.assertEqual(first_files, second_files)
            compiler.verify_pack(first, expected_entity="kael")

    def test_codex_pack_combines_soul_rules_memory_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.compile("velvet-coder", Path(directory))
            context = (pack / "CODEX.AGENTS.md").read_text(encoding="utf-8")
            schema = json.loads((pack / "output.schema.json").read_text(encoding="utf-8"))
        self.assertIn("Entity ID: `velvet-coder`", context)
        self.assertIn("# Velvet Coder", context)
        self.assertIn("Stellmaria/Velvet", context)
        self.assertIn("начальная память", context)
        self.assertEqual("object", schema["type"])
        self.assertIn("memory_candidates", schema["required"])

    def test_project_sources_are_not_cross_wired(self) -> None:
        manifest = compiler.load_manifest(ROOT)
        velvet = json.dumps(manifest["entities"]["velvet-coder"], ensure_ascii=False)
        maximum = json.dumps(manifest["entities"]["max-coder"], ensure_ascii=False)
        for marker in ("SOUL.max.md", "AGENTS.max.md", "projects/max.md"):
            self.assertNotIn(marker, velvet)
        for marker in ("SOUL.velvet.md", "AGENTS.velvet.md", "projects/velvet.md"):
            self.assertNotIn(marker, maximum)

    def test_librarian_pack_has_no_memory_or_skills(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.compile("velvet-librarian", Path(directory))
            manifest = compiler.verify_pack(pack, expected_entity="velvet-librarian")
            names = {path.name for path in pack.iterdir()}
        self.assertNotIn("MEMORY.seed.md", names)
        self.assertNotIn("USER.seed.md", names)
        self.assertNotIn("skills", names)
        self.assertEqual([], manifest["skills"])

    def test_secret_like_vault_material_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "brain-vault"
            vault.mkdir()
            (vault / "README.md").write_text(
                "token=" + "ghp_" + "abcdefghijklmnopqrstuvwxyz123456\n",
                encoding="utf-8",
            )
            with self.assertRaises(compiler.BrainError):
                compiler.validate_vault(root)

    def test_tampered_pack_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.compile("kael", Path(directory))
            (pack / "AGENTS.md").write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(compiler.BrainError):
                compiler.verify_pack(pack, expected_entity="kael")

    def test_compiled_context_budget_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            oversized = Path(directory) / "AGENTS.md"
            oversized.write_bytes(b"x" * (compiler.MAX_ENTITY_CONTEXT_BYTES + 1))
            with self.assertRaises(compiler.BrainError):
                compiler._enforce_context_budget(
                    "test-entity",
                    [oversized],
                    label="test",
                )


class BrainRuntimeInstallationTests(unittest.TestCase):
    def test_hermes_install_preserves_live_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack = root / "pack"
            target = root / "target"
            target.mkdir()
            (target / "MEMORY.md").write_text("live memory\n", encoding="utf-8")
            compiler.compile_entity(ROOT, "kael", pack)
            installer.install_pack(pack, target, entity="kael", mode="hermes")
            runtime_verifier.verify_installed(target, entity="kael", mode="hermes")
            self.assertEqual("live memory\n", (target / "MEMORY.md").read_text(encoding="utf-8"))

    def test_codex_install_activates_global_agents_and_scoped_skills(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack = root / "pack"
            target = root / "target"
            target.mkdir()
            compiler.compile_entity(ROOT, "max-coder", pack)
            installer.install_pack(pack, target, entity="max-coder", mode="codex")
            runtime_verifier.verify_installed(target, entity="max-coder", mode="codex")
            agents = (target / "AGENTS.md").read_text(encoding="utf-8")
            skills = {path.name for path in (target / ".agents" / "skills").iterdir()}
        self.assertIn("Entity ID: `max-coder`", agents)
        self.assertIn("orchestrated-task", skills)
        self.assertNotIn("server-diagnostics", skills)

    def test_librarian_profile_uses_compiled_context_and_remains_deny_all(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack = root / "pack"
            target = root / "target"
            source_config = root / "config.yaml"
            source_config.write_text(
                json.dumps(
                    {"model": {"provider": "custom", "default": "source-model"}}
                ),
                encoding="utf-8",
            )
            compiler.compile_entity(ROOT, "velvet-librarian", pack)
            librarian_profile.prepare(
                source_config,
                target,
                pack / "SOUL.md",
                pack / "AGENTS.md",
                pack / "context-manifest.json",
            )
            config = librarian_profile.yaml.safe_load(
                (target / "config.yaml").read_text(encoding="utf-8")
            )
            manifest = json.loads(
                (target / "context-manifest.json").read_text(encoding="utf-8")
            )
        self.assertEqual([], config["platform_toolsets"]["api_server"])
        self.assertIn("terminal", config["agent"]["disabled_toolsets"])
        self.assertIn("skills", config["agent"]["disabled_toolsets"])
        self.assertTrue(config["compression"]["enabled"])
        self.assertTrue(config["tool_loop_guardrails"]["hard_stop_enabled"])
        self.assertEqual("velvet-librarian", manifest["entity_id"])


if __name__ == "__main__":
    unittest.main()
