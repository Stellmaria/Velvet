from __future__ import annotations

import ast
import unittest
from pathlib import Path

from velvet_bot.presentation.telegram.runtime_contracts import (
    COMPATIBILITY_CONTRACTS,
    contract_names,
)

ROOT = Path(__file__).resolve().parents[1]
COMPAT_PATH = ROOT / "velvet_bot/presentation/telegram/compat.py"
INVENTORY_DOC = ROOT / "docs/runtime_compatibility_inventory.md"


def _literal_assignment(name: str) -> tuple[str, ...]:
    tree = ast.parse(COMPAT_PATH.read_text(encoding="utf-8"), filename=str(COMPAT_PATH))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            return tuple(str(item) for item in ast.literal_eval(node.value))
    raise AssertionError(f"Не найдено literal assignment {name!r}")


class RuntimeCompatibilityContractTests(unittest.TestCase):
    def test_every_active_component_has_exactly_one_contract(self) -> None:
        pre_import = _literal_assignment("PRE_IMPORT_COMPONENTS")
        post_import = _literal_assignment("POST_IMPORT_COMPONENTS")
        active = pre_import + post_import
        names = tuple(contract.name for contract in COMPATIBILITY_CONTRACTS)

        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(active, names)
        self.assertEqual(pre_import, contract_names("pre-import"))
        self.assertEqual(post_import, contract_names("post-import"))

    def test_active_monkeypatches_have_retirement_decisions(self) -> None:
        for contract in COMPATIBILITY_CONTRACTS:
            with self.subTest(component=contract.name):
                self.assertEqual(
                    "remove-after-consumer-migration",
                    contract.decision,
                )
                self.assertTrue(contract.owner_module.startswith("velvet_bot."))
                self.assertTrue(contract.consumers)
                self.assertTrue(contract.side_effect.strip())
                self.assertTrue(contract.replacement.strip())

    def test_human_inventory_mentions_every_component(self) -> None:
        text = INVENTORY_DOC.read_text(encoding="utf-8")

        for contract in COMPATIBILITY_CONTRACTS:
            with self.subTest(component=contract.name):
                self.assertEqual(1, text.count(f"`{contract.name}` |"))


if __name__ == "__main__":
    unittest.main()
