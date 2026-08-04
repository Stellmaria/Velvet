from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"Expected one match in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    purchase = "velvet_bot/domains/auf_wallet/purchase.py"
    replace_once(purchase, "from dataclasses import dataclass\n", "from dataclasses import dataclass, replace\n")
    replace_once(
        purchase,
        "from .models import AufWallet\nfrom .service import AUF_PACKAGES\nfrom .store import _ensure_wallet, _wallet_from_row\n",
        "from .models import AufWallet\n"
        "from .package_pricing import active_package_price\n"
        "from .service import AUF_PACKAGES\n"
        "from .store import (\n"
        "    _ensure_wallet,\n"
        "    _wallet_from_row,\n"
        "    set_invoice_currency_usd,\n"
        ")\n",
    )
    replace_once(
        purchase,
        "        key = _idempotency_key(idempotency_key)\n        async with self._database.acquire() as connection:\n",
        "        key = _idempotency_key(idempotency_key)\n"
        "        fixed_rub = await active_package_price(self._database, amount)\n"
        "        async with self._database.acquire() as connection:\n",
    )
    replace_once(
        purchase,
        "                retail = Decimal(settings[\"retail_auf_usd\"])\n"
        "                rate = Decimal(settings[\"billing_usd_to_rub\"])\n"
        "                usd = (Decimal(amount) * retail).quantize(Decimal(\"0.01\"))\n"
        "                local = _round_rub(usd * rate)\n",
        "                retail = Decimal(settings[\"retail_auf_usd\"])\n"
        "                rate = Decimal(settings[\"billing_usd_to_rub\"])\n"
        "                if fixed_rub is None:\n"
        "                    usd = (Decimal(amount) * retail).quantize(Decimal(\"0.01\"))\n"
        "                    local = _round_rub(usd * rate)\n"
        "                else:\n"
        "                    local = Decimal(fixed_rub).quantize(Decimal(\"0.01\"))\n"
        "                    usd = (local / rate).quantize(\n"
        "                        Decimal(\"0.01\"),\n"
        "                        rounding=ROUND_HALF_UP,\n"
        "                    )\n",
    )
    marker = "    async def recent_invoices(\n"
    repository_method = (
        "    async def set_currency_usd(\n"
        "        self,\n"
        "        *,\n"
        "        invoice_id: UUID,\n"
        "    ) -> Decimal | None:\n"
        "        return await set_invoice_currency_usd(\n"
        "            self._database,\n"
        "            invoice_id=invoice_id,\n"
        "        )\n\n"
    )
    replace_once(purchase, marker, repository_method + marker)
    replace_once(
        purchase,
        "        actor_user_id: int,\n        idempotency_key: str,\n    ) -> AufPurchaseInvoice:\n",
        "        actor_user_id: int,\n"
        "        idempotency_key: str,\n"
        "        billing_currency: str = \"RUB\",\n"
        "    ) -> AufPurchaseInvoice:\n",
    )
    replace_once(
        purchase,
        "        return await self._repository.create_invoice(\n"
        "            workspace_id=int(workspace_id),\n"
        "            package_auf=int(package_auf),\n"
        "            actor_user_id=int(actor_user_id),\n"
        "            idempotency_key=idempotency_key,\n"
        "        )\n",
        "        currency = _billing_currency(billing_currency)\n"
        "        invoice = await self._repository.create_invoice(\n"
        "            workspace_id=int(workspace_id),\n"
        "            package_auf=int(package_auf),\n"
        "            actor_user_id=int(actor_user_id),\n"
        "            idempotency_key=idempotency_key,\n"
        "        )\n"
        "        if currency == \"RUB\" or invoice.billing_currency == \"USD\":\n"
        "            return invoice\n"
        "        usd_amount = await self._repository.set_currency_usd(\n"
        "            invoice_id=invoice.id,\n"
        "        )\n"
        "        if usd_amount is None:\n"
        "            raise RuntimeError(\"Не удалось зафиксировать валюту счёта.\")\n"
        "        return replace(\n"
        "            invoice,\n"
        "            package_price_usd=usd_amount,\n"
        "            billing_currency=\"USD\",\n"
        "            final_local_amount=usd_amount,\n"
        "        )\n",
    )
    replace_once(
        purchase,
        "def _idempotency_key(value: str) -> str:\n",
        "def _billing_currency(value: str) -> str:\n"
        "    currency = str(value or \"\").strip().upper()\n"
        "    if currency not in {\"RUB\", \"USD\"}:\n"
        "        raise ValueError(\"Поддерживаются только RUB и USD.\")\n"
        "    return currency\n\n\n"
        "def _idempotency_key(value: str) -> str:\n",
    )

    store = "velvet_bot/domains/auf_wallet/store.py"
    replace_once(
        store,
        "\n\nasync def _ensure_wallet(connection: Any, *, workspace_id: int, for_update: bool = False):\n",
        "\n\nasync def set_invoice_currency_usd(\n"
        "    database: Database,\n"
        "    *,\n"
        "    invoice_id: UUID,\n"
        ") -> Decimal | None:\n"
        "    async with database.acquire() as connection:\n"
        "        value = await connection.fetchval(\n"
        "            \"\"\"\n"
        "            UPDATE auf_purchase_invoices\n"
        "            SET billing_currency = 'USD',\n"
        "                final_local_amount = package_price_usd,\n"
        "                updated_at = NOW()\n"
        "            WHERE id = $1::UUID\n"
        "              AND status = 'created'\n"
        "            RETURNING package_price_usd\n"
        "            \"\"\",\n"
        "            invoice_id,\n"
        "        )\n"
        "    return Decimal(value) if value is not None else None\n"
        "\n\nasync def _ensure_wallet(connection: Any, *, workspace_id: int, for_update: bool = False):\n",
    )
    replace_once(
        store,
        "__all__ = (\"AufWalletRepository\",)\n",
        "__all__ = (\"AufWalletRepository\", \"set_invoice_currency_usd\")\n",
    )

    ui = ROOT / "velvet_bot/app/auf_wallet_currency_ui.py"
    ui_text = ui.read_text(encoding="utf-8")
    ui_text = ui_text.replace("from dataclasses import replace\n", "")
    ui_text, count = re.subn(
        r"\nasync def _set_invoice_currency\(.*?\n\nasync def _notify_owner_purchase_intent\(",
        "\n\nasync def _notify_owner_purchase_intent(",
        ui_text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("Could not remove UI persistence helper")
    old_create = (
        "            invoice = await auf_purchase_service.create_invoice(\n"
        "                workspace_id=workspace_id,\n"
        "                package_auf=package_auf,\n"
        "                actor_user_id=callback.from_user.id,\n"
        "                idempotency_key=f\"telegram-wallet-invoice:{callback.id}\",\n"
        "            )\n"
        "            invoice = await _set_invoice_currency(\n"
        "                auf_purchase_service,\n"
        "                invoice,\n"
        "                selected_currency,\n"
        "            )\n"
    )
    new_create = (
        "            invoice = await auf_purchase_service.create_invoice(\n"
        "                workspace_id=workspace_id,\n"
        "                package_auf=package_auf,\n"
        "                actor_user_id=callback.from_user.id,\n"
        "                idempotency_key=f\"telegram-wallet-invoice:{callback.id}\",\n"
        "                billing_currency=selected_currency,\n"
        "            )\n"
    )
    if ui_text.count(old_create) != 1:
        raise RuntimeError("Could not replace invoice creation in currency UI")
    ui.write_text(ui_text.replace(old_create, new_create, 1), encoding="utf-8")

    installer = ROOT / "velvet_bot/app/auf_wallet_ui_install.py"
    installer.write_text(
        "from __future__ import annotations\n\n"
        "import importlib\n\n"
        "from velvet_bot.app.auf_wallet_currency_ui import (\n"
        "    handle_auf_wallet_action,\n"
        ")\n\n"
        "_INSTALLED = False\n\n\n"
        "def install_auf_wallet_ui() -> None:\n"
        "    \"\"\"Route Auf wallet callbacks before the historical generic action handler.\"\"\"\n\n"
        "    global _INSTALLED\n"
        "    if _INSTALLED:\n"
        "        return\n\n"
        "    controller = importlib.import_module(\n"
        "        \"velvet_bot.presentation.telegram.workspace_home_controller\"\n"
        "    )\n"
        "    original = controller.handle_scoped_auf_action\n\n"
        "    async def handle_scoped_auf_action_with_wallet(\n"
        "        callback,\n"
        "        callback_data,\n"
        "        state,\n"
        "        access_policy,\n"
        "        kie_settings,\n"
        "        database,\n"
        "        ai_usage_service,\n"
        "        ai_task_queue_service,\n"
        "        auf_runtime_service,\n"
        "        auf_wallet_service,\n"
        "        auf_purchase_service,\n"
        "    ) -> None:\n"
        "        if callback_data.action.startswith(\"wallet\"):\n"
        "            await handle_auf_wallet_action(\n"
        "                callback,\n"
        "                callback_data,\n"
        "                state,\n"
        "                auf_wallet_service,\n"
        "                auf_purchase_service,\n"
        "            )\n"
        "            return\n"
        "        await original(\n"
        "            callback,\n"
        "            callback_data,\n"
        "            state,\n"
        "            access_policy,\n"
        "            kie_settings,\n"
        "            database,\n"
        "            ai_usage_service,\n"
        "            ai_task_queue_service,\n"
        "            auf_runtime_service, auf_wallet_service, auf_purchase_service,\n"
        "        )\n\n"
        "    controller.handle_scoped_auf_action = handle_scoped_auf_action_with_wallet\n"
        "    _INSTALLED = True\n\n\n"
        "__all__ = (\"install_auf_wallet_ui\",)\n",
        encoding="utf-8",
    )

    (ROOT / "velvet_bot/app/auf_wallet_currency_fix.py").unlink(missing_ok=True)

    currency_test = ROOT / "tests/test_auf_wallet_currency.py"
    currency_test.write_text(
        "from __future__ import annotations\n\n"
        "import inspect\n"
        "import unittest\n"
        "from decimal import Decimal\n\n"
        "from velvet_bot.app import auf_wallet_currency_ui as currency_ui\n"
        "from velvet_bot.app import auf_wallet_ui_install\n\n\n"
        "class AufWalletCurrencyTests(unittest.TestCase):\n"
        "    def test_currency_normalization_and_callback_compatibility(self) -> None:\n"
        "        self.assertEqual(\"USD\", currency_ui._normalize_currency(\"usd\"))\n"
        "        self.assertEqual(\"RUB\", currency_ui._normalize_currency(\"eur\"))\n"
        "        self.assertEqual(\"20:USD\", currency_ui._package_callback_value(20, \"usd\"))\n"
        "        self.assertEqual((20, \"USD\"), currency_ui._parse_package_callback_value(\"20:USD\"))\n"
        "        self.assertEqual((40, \"RUB\"), currency_ui._parse_package_callback_value(\"40\"))\n\n"
        "    def test_money_format_uses_selected_currency(self) -> None:\n"
        "        self.assertEqual(\"100 ₽\", currency_ui._format_money(Decimal(\"100\"), \"RUB\"))\n"
        "        self.assertEqual(\"$5.37\", currency_ui._format_money(Decimal(\"5.37\"), \"USD\"))\n\n"
        "    def test_wallet_displays_both_prices_and_routes_currency_to_service(self) -> None:\n"
        "        render_source = inspect.getsource(currency_ui._render_wallet)\n"
        "        handler_source = inspect.getsource(currency_ui.handle_auf_wallet_action)\n"
        "        self.assertIn(\"quote.price_rub\", render_source)\n"
        "        self.assertIn(\"quote.price_usd\", render_source)\n"
        "        self.assertIn(\"Валюта нового счёта\", render_source)\n"
        "        self.assertIn(\"billing_currency=selected_currency\", handler_source)\n"
        "        self.assertNotIn(\"database.acquire\", inspect.getsource(currency_ui))\n\n"
        "    def test_installer_routes_directly_to_currency_ui(self) -> None:\n"
        "        source = inspect.getsource(auf_wallet_ui_install)\n"
        "        self.assertIn(\"auf_wallet_currency_ui\", source)\n"
        "        self.assertNotIn(\"auf_wallet_currency_fix\", source)\n\n\n"
        "if __name__ == \"__main__\":\n"
        "    unittest.main()\n",
        encoding="utf-8",
    )

    invoice_test = "tests/test_auf_purchase_invoices.py"
    replace_once(
        invoice_test,
        "    async def _invoice(self, *, key: str, package: int = 100):\n"
        "        return await self.service.create_invoice(\n"
        "            workspace_id=DEFAULT_WORKSPACE_ID,\n"
        "            package_auf=package,\n"
        "            actor_user_id=77,\n"
        "            idempotency_key=f\"test:purchase:{key}\",\n"
        "        )\n",
        "    async def _invoice(\n"
        "        self,\n"
        "        *,\n"
        "        key: str,\n"
        "        package: int = 100,\n"
        "        currency: str = \"RUB\",\n"
        "    ):\n"
        "        return await self.service.create_invoice(\n"
        "            workspace_id=DEFAULT_WORKSPACE_ID,\n"
        "            package_auf=package,\n"
        "            actor_user_id=77,\n"
        "            idempotency_key=f\"test:purchase:{key}\",\n"
        "            billing_currency=currency,\n"
        "        )\n",
    )
    replace_once(
        invoice_test,
        "    async def test_invoice_creation_is_idempotent(self) -> None:\n",
        "    async def test_usd_invoice_uses_fixed_package_price(self) -> None:\n"
        "        invoice = await self._invoice(key=\"usd\", package=100, currency=\"USD\")\n"
        "        self.assertEqual(\"USD\", invoice.billing_currency)\n"
        "        self.assertEqual(Decimal(\"5.37000000\"), invoice.package_price_usd)\n"
        "        self.assertEqual(Decimal(\"5.37\"), invoice.final_local_amount)\n"
        "        self.assertEqual(Decimal(\"79.85000000\"), invoice.locked_exchange_rate)\n\n"
        "    async def test_invoice_creation_is_idempotent(self) -> None:\n",
    )

    charging = ROOT / "tests/test_auf_task_charging.py"
    charging_text = charging.read_text(encoding="utf-8")
    charging_text = charging_text.replace(
        "async def test_price_catalog_uses_provider_plus_thirty_whole_values",
        "async def test_price_catalog_uses_global_margin_policy_whole_values",
        1,
    )
    for old, new in (("Decimal(\"5\")", "Decimal(\"4\")"), ("Decimal(\"9\")", "Decimal(\"7\")"), ("Decimal(\"29\")", "Decimal(\"21\")")):
        charging_text = charging_text.replace(old, new, 1)
    charging.write_text(charging_text, encoding="utf-8")


if __name__ == "__main__":
    main()
