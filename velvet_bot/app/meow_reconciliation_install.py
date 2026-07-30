from __future__ import annotations

import importlib
from html import escape
from typing import Any

from velvet_bot.domains.meow_wallet import MeowPurchaseRepository
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.workers import PeriodicWorkerSpec

_INSTALLED = False


def install_meow_reconciliation() -> None:
    """Register hourly expiry and consistency checks for the Auf economy."""

    global _INSTALLED
    if _INSTALLED:
        return

    workers = importlib.import_module("velvet_bot.app.workers")
    bootstrap = importlib.import_module("velvet_bot.app.bootstrap")
    original = workers.build_worker_manager

    def build_worker_manager_with_reconciliation(*args: Any, **kwargs: Any):
        manager = original(*args, **kwargs)
        database = kwargs.get("database")
        bot = kwargs.get("bot")
        if database is None or bot is None:
            return manager
        repository = MeowPurchaseRepository(database)

        async def reconcile_auf_economy() -> None:
            expired = await repository.expire_invoices()
            issues = await repository.reconciliation_issues(limit=50)
            if not issues:
                await repository.mark_reconciliation_checked()
                return
            if not await repository.claim_reconciliation_notice(issues):
                return
            lines = [
                "<b>⚠️ Сверка экономики Ауф</b>",
                "",
                f"Обнаружено расхождений: <b>{len(issues)}</b>.",
            ]
            if expired:
                lines.append(f"Просрочено счетов за проход: <b>{expired}</b>.")
            lines.append("")
            for item in issues[:20]:
                workspace = (
                    f"пространство {item.workspace_id}"
                    if item.workspace_id is not None
                    else "без пространства"
                )
                lines.append(
                    f"• <code>{escape(item.code)}</code> · {escape(workspace)} · "
                    f"<code>{escape(item.reference)}</code>\n"
                    f"  {escape(item.details)}"
                )
            if len(issues) > 20:
                lines.append(f"\nИ ещё: <b>{len(issues) - 20}</b>.")
            await bot.send_message(
                GLOBAL_WORKSPACE_CREATOR_ID,
                "\n".join(lines),
            )

        manager.register(
            PeriodicWorkerSpec(
                name="meow-auf-reconciliation",
                description="Сверка кошельков, резервов и счетов Ауф",
                interval_seconds=3600,
                runner=reconcile_auf_economy,
            )
        )
        return manager

    workers.build_worker_manager = build_worker_manager_with_reconciliation
    bootstrap.build_worker_manager = build_worker_manager_with_reconciliation
    _INSTALLED = True


__all__ = ("install_meow_reconciliation",)
