from __future__ import annotations

import asyncio
import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path

import velvet_bot.presentation.telegram.shared.deletion as deletion
import velvet_bot.presentation.telegram.shared.editing as editing
from velvet_bot.presentation.telegram.shared.navigation import (
    NavigationButton,
    build_back_refresh_keyboard,
    build_pagination_keyboard,
)
from velvet_bot.presentation.telegram.shared.text import chunk_telegram_text

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_SCRIPT = ROOT / "scripts" / "inventory_telegram_helpers.py"


class FakeTelegramBadRequest(Exception):
    pass


class FakeMessage:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.edit_calls: list[tuple[str, object, dict[str, object]]] = []
        self.delete_calls = 0

    async def edit_text(self, text: str, *, reply_markup=None, **kwargs):
        self.edit_calls.append((text, reply_markup, kwargs))
        if self.error is not None:
            raise self.error
        return self

    async def delete(self) -> None:
        self.delete_calls += 1
        if self.error is not None:
            raise self.error


class SharedEditingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_edit_bad_request = editing.TelegramBadRequest
        self.original_delete_bad_request = deletion.TelegramBadRequest
        editing.TelegramBadRequest = FakeTelegramBadRequest
        deletion.TelegramBadRequest = FakeTelegramBadRequest

    def tearDown(self) -> None:
        editing.TelegramBadRequest = self.original_edit_bad_request
        deletion.TelegramBadRequest = self.original_delete_bad_request

    async def test_message_not_modified_is_the_only_ignored_edit_error(self) -> None:
        message = FakeMessage(FakeTelegramBadRequest("Bad Request: message is not modified"))

        changed = await editing.safe_edit_message_text(
            message,
            "text",
            reply_markup="keyboard",
        )

        self.assertFalse(changed)
        self.assertEqual(message.edit_calls, [("text", "keyboard", {})])

    async def test_other_edit_errors_are_reraised(self) -> None:
        error = FakeTelegramBadRequest("Bad Request: message to edit not found")
        message = FakeMessage(error)

        with self.assertRaises(FakeTelegramBadRequest) as captured:
            await editing.safe_edit_message_text(message, "text")

        self.assertIs(captured.exception, error)

    async def test_runtime_and_cancellation_errors_are_not_swallowed(self) -> None:
        for error in (RuntimeError("formatter failed"), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                message = FakeMessage(error)
                with self.assertRaises(type(error)):
                    await editing.safe_edit_message_text(message, "text")

    async def test_deletion_suppresses_only_already_absent_messages(self) -> None:
        missing = FakeMessage(
            FakeTelegramBadRequest("Bad Request: message to delete not found")
        )
        existing = FakeMessage()
        forbidden = FakeMessage(FakeTelegramBadRequest("message can't be deleted"))

        self.assertFalse(await deletion.delete_message_safely(missing))
        self.assertTrue(await deletion.delete_message_safely(existing))
        with self.assertRaises(FakeTelegramBadRequest):
            await deletion.delete_message_safely(forbidden)


class SharedNavigationTests(unittest.TestCase):
    def test_back_refresh_keyboard_preserves_callback_contracts(self) -> None:
        keyboard = build_back_refresh_keyboard(
            back=NavigationButton(text="↩️ Назад", callback_data="area:back"),
            refresh_callback_data="area:refresh",
        )

        row = keyboard.inline_keyboard[0]
        self.assertEqual([button.callback_data for button in row], ["area:back", "area:refresh"])

    def test_pagination_uses_one_based_boundaries(self) -> None:
        keyboard = build_pagination_keyboard(
            page=2,
            total_pages=3,
            callback_for_page=lambda page: f"items:{page}",
            back=NavigationButton(text="↩️ Назад", callback_data="items:back"),
        )

        self.assertEqual(
            [button.callback_data for button in keyboard.inline_keyboard[0]],
            ["items:1", "items:2", "items:3"],
        )
        self.assertEqual(keyboard.inline_keyboard[1][0].callback_data, "items:back")


class SharedTextTests(unittest.TestCase):
    def test_chunking_preserves_content_and_limit(self) -> None:
        text = "first paragraph\n\n" + ("second line " * 30)

        chunks = chunk_telegram_text(text, limit=80)

        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk) <= 80 for chunk in chunks))
        self.assertEqual("".join(chunks).replace("\n\n", ""), text.replace("\n\n", ""))


class SharedExceptionBoundaryTests(unittest.TestCase):
    def test_shared_editing_and_media_have_no_broad_except(self) -> None:
        for relative in (
            "velvet_bot/presentation/telegram/shared/editing.py",
            "velvet_bot/presentation/telegram/shared/media.py",
        ):
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
            broad = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.ExceptHandler)
                and isinstance(node.type, ast.Name)
                and node.type.id in {"Exception", "BaseException"}
            ]
            self.assertEqual(broad, [], relative)


class TelegramHelperInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        completed = subprocess.run(
            [sys.executable, str(INVENTORY_SCRIPT), "--check", "--json"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode:
            raise AssertionError(
                "Shared contract inventory failed:\n"
                + completed.stderr
                + "\n"
                + completed.stdout
            )
        cls.inventory = json.loads(completed.stdout)

    def test_all_requested_families_have_owned_contracts(self) -> None:
        contracts = self.inventory["contracts"]
        self.assertGreaterEqual(len(contracts), 14)
        for contract in contracts:
            with self.subTest(family=contract["family"]):
                self.assertTrue(contract["current_owner"])
                self.assertTrue(contract["target_contract"])
                self.assertTrue(contract["retirement_issue"])
                self.assertNotIn("hotfix", contract["target_contract"])
                self.assertNotIn("_install", contract["target_contract"])

    def test_known_private_contracts_are_migrated(self) -> None:
        required = {
            "_task_line",
            "_load_user_tasks",
            "_task_list_keyboard",
            "_MODEL_NAMES",
            "_edit_or_answer",
            "_validated_model",
            "_reference_from_data",
        }
        known = {
            item["private_name"]: item
            for item in self.inventory["known_private_contracts"]
        }
        self.assertTrue(required.issubset(known))
        for private_name in required:
            with self.subTest(private_name=private_name):
                self.assertEqual(known[private_name]["status"], "migrated")

    def test_exact_normalized_and_semantic_duplicates_are_classified(self) -> None:
        valid = {
            "real-duplicate",
            "normalized-near-duplicate",
            "semantic-near-duplicate",
            "generated/compat",
            "allowed-template",
        }
        for key in (
            "exact_duplicate_groups",
            "normalized_duplicate_groups",
            "semantic_near_duplicate_groups",
        ):
            for group in self.inventory[key]:
                with self.subTest(key=key, digest=group["digest"]):
                    self.assertIn(group["kind"], valid)
                    self.assertTrue(group["family"])
                    self.assertGreaterEqual(len(group["occurrences"]), 2)

    def test_image_and_video_delivery_near_duplicates_are_visible(self) -> None:
        groups = self.inventory["semantic_near_duplicate_groups"]
        self.assertTrue(
            any(
                group["family"] == "media download/preview/original delivery"
                and len(group["occurrences"]) >= 2
                for group in groups
            )
        )

    def test_blocking_contract_and_shared_boundary_debt_is_zero(self) -> None:
        self.assertEqual(self.inventory["blocking_private_contract_access_count"], 0)
        self.assertEqual(self.inventory["shared_contract_violations"], [])

    def test_legacy_analytics_facade_delegates_to_shared_editor(self) -> None:
        source = (ROOT / "velvet_bot" / "safe_analytics_edit.py").read_text(encoding="utf-8")
        self.assertIn("safe_edit_callback_text", source)
        self.assertNotIn("message is not modified", source)


if __name__ == "__main__":
    unittest.main()
