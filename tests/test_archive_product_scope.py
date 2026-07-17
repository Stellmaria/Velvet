from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOT = ROOT / "velvet_bot"

_BANNED_MODULE_PARTS = {"auction", "auctions", "bidding"}
_BANNED_SYMBOLS = {
    "Auction",
    "AuctionRepository",
    "AuctionService",
    "AuctionType",
    "Bid",
    "BidRepository",
    "BidService",
    "Bidder",
    "Lot",
    "ReverseAuction",
}
_BANNED_IDENTIFIERS = {
    "auction_id",
    "auction_type",
    "bid_amount",
    "bid_id",
    "lot_id",
    "maximum_bid",
    "minimum_bid",
    "reverse_auction",
}


class ArchiveProductScopeTests(unittest.TestCase):
    def test_production_package_has_no_auction_domain_dependencies(self) -> None:
        violations: list[str] = []

        for path in sorted(PRODUCTION_ROOT.rglob("*.py")):
            relative = path.relative_to(ROOT)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        parts = set(alias.name.lower().split("."))
                        if parts & _BANNED_MODULE_PARTS:
                            violations.append(f"{relative}:{node.lineno}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = (node.module or "").lower()
                    if set(module.split(".")) & _BANNED_MODULE_PARTS:
                        violations.append(f"{relative}:{node.lineno}: from {module}")
                    for alias in node.names:
                        if alias.name in _BANNED_SYMBOLS:
                            violations.append(
                                f"{relative}:{node.lineno}: import symbol {alias.name}"
                            )
                elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name in _BANNED_SYMBOLS:
                        violations.append(f"{relative}:{node.lineno}: declaration {node.name}")
                elif isinstance(node, ast.Name):
                    if node.id in _BANNED_IDENTIFIERS:
                        violations.append(f"{relative}:{node.lineno}: identifier {node.id}")
                elif isinstance(node, ast.arg):
                    if node.arg in _BANNED_IDENTIFIERS:
                        violations.append(f"{relative}:{node.lineno}: argument {node.arg}")

        self.assertEqual(
            violations,
            [],
            "Velvet Archive must remain isolated from the auction-bot domain:\n"
            + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
