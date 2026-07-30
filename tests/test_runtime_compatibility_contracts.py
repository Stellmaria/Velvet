from __future__ import annotations

import unittest
from pathlib import Path

from velvet_bot.presentation.telegram.compat import (
    ACTIVE_COMPATIBILITY_COMPONENTS,
    POST_IMPORT_COMPONENTS,
    PRE_IMPORT_COMPONENTS,
)
from velvet_bot.presentation.telegram.compatibility_contracts import (
    COMPATIBILITY_CONTRACTS,
    contract_names,
)

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_DOC = ROOT / "docs/runtime_compatibility_inventory.md"


class RuntimeCompatibilityContractTests(unittest.TestCase):
    def test_every_active_component_has_exactly_one_contract(self) -> None:
        names = tuple(contract.name for contract in COMPATIBILITY_CONTRACTS)

        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(ACTIVE_COMPATIBILITY_COMPONENTS, names)
        self.assertEqual(PRE_IMPORT_COMPONENTS, contract_names("pre-import"))
        self.assertEqual(POST_IMPORT_COMPONENTS, contract_names("post-import"))

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
