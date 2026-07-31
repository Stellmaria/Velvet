from __future__ import annotations

import asyncio
import inspect
import logging
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from velvet_bot.app import workspace_owner_generation_hotfix as generation_hotfix
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback
from velvet_bot.presentation.telegram.routers.workspace_auf_provider_balances import (
    _fetch_byesu_balance,
)
from velvet_bot.presentation.telegram.routers.workspace_auf_root import (
    _build_root_keyboard,
)
from velvet_bot.runtime_stability import is_recoverable_aiogram_polling_record


ROOT = Path(__file__).resolve().parents[1]


def _button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


class AufMenuProviderBalanceHotfixTests(unittest.TestCase):
    def test_owner_root_exposes_provider_balances_only_to_global_owner(self) -> None:
        owner = _build_root_keyboard(
            workspace_id=42,
            enabled=True,
            grs_enabled=True,
            global_owner=True,
            module_visible=True,
        )
        member = _build_root_keyboard(
            workspace_id=42,
            enabled=True,
            grs_enabled=True,
            global_owner=False,
            module_visible=True,
        )

        self.assertIn("📊 Балансы API · Стэл", _button_texts(owner))
        self.assertNotIn("📊 Балансы API · Стэл", _button_texts(member))
        provider_button = next(
            button
            for row in owner.inline_keyboard
            for button in row
            if button.text == "📊 Балансы API · Стэл"
        )
        parsed = AufCallback.unpack(provider_button.callback_data)
        self.assertEqual("provider_balances", parsed.action)
        self.assertEqual(42, parsed.workspace_id)

    def test_byesu_balance_uses_documented_billing_response(self) -> None:
        with (
            patch.dict(os.environ, {"BYESU_API_KEY": "sk-test"}, clear=True),
            patch(
                "velvet_bot.presentation.telegram.routers."
                "workspace_auf_provider_balances._read_json",
                return_value={"balance_usd": "12.3456"},
            ),
        ):
            balance = asyncio.run(_fetch_byesu_balance())

        self.assertEqual("12.3456", str(balance.value))
        self.assertEqual("$", balance.unit)
        self.assertIsNone(balance.error)

    def test_canonical_callback_handler_has_explicit_dependency_signature(self) -> None:
        source = inspect.getsource(generation_hotfix._install_canonical_photo_route)
        self.assertNotIn("handle_scoped_auf_photo_action(*args", source)
        for parameter in (
            "callback_data",
            "state",
            "kie_settings",
            "auf_runtime_service",
            "auf_wallet_service",
            "auf_purchase_service",
        ):
            self.assertIn(parameter, source)

    def test_provider_callback_is_registered_before_generic_auf_handlers(self) -> None:
        source = (
            ROOT / "velvet_bot/app/auf_workspace_ui_install.py"
        ).read_text(encoding="utf-8")
        provider_registration = "router.callback_query.register(\n            handle_auf_provider_balances"
        self.assertIn(provider_registration, source)
        self.assertLess(
            source.index(provider_registration),
            source.index("original_register(router)"),
        )


class ExpectedShutdownLoggingTests(unittest.TestCase):
    def test_sigterm_notice_is_not_an_incident(self) -> None:
        record = logging.LogRecord(
            name="aiogram.dispatcher",
            level=logging.WARNING,
            pathname="dispatcher.py",
            lineno=1,
            msg="Received SIGTERM signal",
            args=(),
            exc_info=None,
        )
        self.assertTrue(is_recoverable_aiogram_polling_record(record))

    def test_unrelated_dispatcher_warning_is_not_suppressed(self) -> None:
        record = logging.LogRecord(
            name="aiogram.dispatcher",
            level=logging.WARNING,
            pathname="dispatcher.py",
            lineno=1,
            msg="Dispatcher queue is corrupted",
            args=(),
            exc_info=None,
        )
        self.assertFalse(is_recoverable_aiogram_polling_record(record))

    def test_legacy_cleanup_includes_sigterm_incidents(self) -> None:
        source = (ROOT / "velvet_bot/runtime_stability.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("received sigterm signal%", source)
        self.assertIn("received sigint signal%", source)


if __name__ == "__main__":
    unittest.main()
