from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping
from uuid import UUID

from velvet_bot.database import Database

from .models import (
    MeowEconomySettings,
    MeowInsufficientBalance,
    MeowWallet,
    MeowWalletEntry,
    MeowWalletOperation,
    MeowWalletOverview,
    MeowWalletStatus,
)


class MeowWalletRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def economy_settings(self) -> MeowEconomySettings:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT provider_auf_usd, retail_auf_usd, billing_usd_to_rub,
                       updated_by_user_id, updated_at
                FROM meow_economy_settings
                WHERE singleton_id = 1
                """
            )
        if row is None:
            raise RuntimeError("Настройки экономики Ауф не инициализированы.")
        return _settings_from_row(row)

    async def update_economy_settings(
        self,
        *,
        provider_auf_usd: Decimal,
        retail_auf_usd: Decimal,
        billing_usd_to_rub: Decimal,
        updated_by_user_id: int,
    ) -> MeowEconomySettings:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE meow_economy_settings
                SET provider_auf_usd = $1::NUMERIC,
                    retail_auf_usd = $2::NUMERIC,
                    billing_usd_to_rub = $3::NUMERIC,
                    updated_by_user_id = $4::BIGINT,
                    updated_at = NOW()
                WHERE singleton_id = 1
                RETURNING provider_auf_usd, retail_auf_usd, billing_usd_to_rub,
                          updated_by_user_id, updated_at
                """,
                provider_auf_usd,
                retail_auf_usd,
                billing_usd_to_rub,
                int(updated_by_user_id),
            )
        if row is None:
            raise RuntimeError("Не удалось обновить настройки экономики Ауф.")
        return _settings_from_row(row)

    async def wallet(self, workspace_id: int) -> MeowWallet:
        async with self._database.acquire() as connection:
            row = await _ensure_wallet(connection, workspace_id=int(workspace_id))
        return _wallet_from_row(row)

    async def overview(
        self,
        workspace_id: int,
        *,
        history_limit: int = 10,
    ) -> MeowWalletOverview:
        safe_limit = max(1, min(50, int(history_limit)))
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        async with self._database.acquire() as connection:
            wallet_row = await _ensure_wallet(connection, workspace_id=int(workspace_id))
            spent = await connection.fetchval(
                """
                SELECT COALESCE(SUM(-amount_units), 0)
                FROM meow_wallet_entries
                WHERE workspace_id = $1::BIGINT
                  AND created_at >= $2::TIMESTAMPTZ
                  AND operation_type IN ('capture', 'manual_debit')
                  AND amount_units < 0
                """,
                int(workspace_id),
                cutoff,
            )
            rows = await connection.fetch(
                """
                SELECT id, workspace_id, operation_type, amount_units,
                       available_after_units, reserved_after_units,
                       actor_user_id, task_id, invoice_id, idempotency_key,
                       comment, metadata, created_at
                FROM meow_wallet_entries
                WHERE workspace_id = $1::BIGINT
                ORDER BY created_at DESC, id DESC
                LIMIT $2::INTEGER
                """,
                int(workspace_id),
                safe_limit,
            )
        return MeowWalletOverview(
            wallet=_wallet_from_row(wallet_row),
            spent_30d_units=int(spent or 0),
            recent_entries=tuple(_entry_from_row(row) for row in rows),
        )

    async def change_available(
        self,
        *,
        workspace_id: int,
        amount_units: int,
        operation_type: MeowWalletOperation,
        idempotency_key: str,
        actor_user_id: int | None,
        comment: str | None = None,
        task_id: UUID | None = None,
        invoice_id: UUID | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> MeowWallet:
        amount = int(amount_units)
        if amount == 0:
            raise ValueError("Операция Ауф не может быть нулевой.")
        key = " ".join(idempotency_key.split())
        if not key or len(key) > 160:
            raise ValueError("Некорректный idempotency key операции Ауф.")

        async with self._database.acquire() as connection:
            async with connection.transaction():
                existing = await connection.fetchval(
                    """
                    SELECT 1
                    FROM meow_wallet_entries
                    WHERE idempotency_key = $1::VARCHAR
                    """,
                    key,
                )
                if existing:
                    row = await _ensure_wallet(
                        connection,
                        workspace_id=int(workspace_id),
                    )
                    return _wallet_from_row(row)

                row = await _ensure_wallet(
                    connection,
                    workspace_id=int(workspace_id),
                    for_update=True,
                )
                available = int(row["available_units"])
                reserved = int(row["reserved_units"])
                updated_available = available + amount
                if updated_available < 0:
                    raise MeowInsufficientBalance(
                        required_units=-amount,
                        available_units=available,
                    )
                wallet_row = await connection.fetchrow(
                    """
                    UPDATE meow_wallets
                    SET available_units = $2::BIGINT,
                        updated_at = NOW()
                    WHERE workspace_id = $1::BIGINT
                    RETURNING workspace_id, available_units, reserved_units,
                              status, created_at, updated_at
                    """,
                    int(workspace_id),
                    updated_available,
                )
                if wallet_row is None:
                    raise RuntimeError("Кошелёк Ауф исчез во время операции.")
                await connection.execute(
                    """
                    INSERT INTO meow_wallet_entries (
                        workspace_id, operation_type, amount_units,
                        available_after_units, reserved_after_units,
                        actor_user_id, task_id, invoice_id,
                        idempotency_key, comment, metadata
                    )
                    VALUES (
                        $1::BIGINT, $2::VARCHAR, $3::BIGINT,
                        $4::BIGINT, $5::BIGINT,
                        $6::BIGINT, $7::UUID, $8::UUID,
                        $9::VARCHAR, $10::TEXT, $11::JSONB
                    )
                    """,
                    int(workspace_id),
                    operation_type.value,
                    amount,
                    updated_available,
                    reserved,
                    int(actor_user_id) if actor_user_id is not None else None,
                    task_id,
                    invoice_id,
                    key,
                    comment.strip() if comment and comment.strip() else None,
                    json.dumps(dict(metadata or {}), ensure_ascii=False, default=str),
                )
        return _wallet_from_row(wallet_row)

    async def set_status(
        self,
        *,
        workspace_id: int,
        status: MeowWalletStatus,
    ) -> MeowWallet:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await _ensure_wallet(connection, workspace_id=int(workspace_id))
                row = await connection.fetchrow(
                    """
                    UPDATE meow_wallets
                    SET status = $2::VARCHAR,
                        updated_at = NOW()
                    WHERE workspace_id = $1::BIGINT
                    RETURNING workspace_id, available_units, reserved_units,
                              status, created_at, updated_at
                    """,
                    int(workspace_id),
                    status.value,
                )
        if row is None:
            raise RuntimeError("Не удалось изменить статус кошелька Ауф.")
        return _wallet_from_row(row)


async def _ensure_wallet(connection: Any, *, workspace_id: int, for_update: bool = False):
    await connection.execute(
        """
        INSERT INTO meow_wallets (workspace_id)
        VALUES ($1::BIGINT)
        ON CONFLICT (workspace_id) DO NOTHING
        """,
        int(workspace_id),
    )
    suffix = " FOR UPDATE" if for_update else ""
    row = await connection.fetchrow(
        """
        SELECT workspace_id, available_units, reserved_units,
               status, created_at, updated_at
        FROM meow_wallets
        WHERE workspace_id = $1::BIGINT
        """ + suffix,
        int(workspace_id),
    )
    if row is None:
        raise RuntimeError("Не удалось создать или загрузить кошелёк Ауф.")
    return row


def _settings_from_row(row: Mapping[str, Any]) -> MeowEconomySettings:
    return MeowEconomySettings(
        provider_auf_usd=Decimal(row["provider_auf_usd"]),
        retail_auf_usd=Decimal(row["retail_auf_usd"]),
        billing_usd_to_rub=Decimal(row["billing_usd_to_rub"]),
        updated_by_user_id=(
            int(row["updated_by_user_id"])
            if row["updated_by_user_id"] is not None
            else None
        ),
        updated_at=row["updated_at"],
    )


def _wallet_from_row(row: Mapping[str, Any]) -> MeowWallet:
    return MeowWallet(
        workspace_id=int(row["workspace_id"]),
        available_units=int(row["available_units"]),
        reserved_units=int(row["reserved_units"]),
        status=MeowWalletStatus(str(row["status"])),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _entry_from_row(row: Mapping[str, Any]) -> MeowWalletEntry:
    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return MeowWalletEntry(
        id=int(row["id"]),
        workspace_id=int(row["workspace_id"]),
        operation_type=MeowWalletOperation(str(row["operation_type"])),
        amount_units=int(row["amount_units"]),
        available_after_units=int(row["available_after_units"]),
        reserved_after_units=int(row["reserved_after_units"]),
        actor_user_id=(
            int(row["actor_user_id"]) if row["actor_user_id"] is not None else None
        ),
        task_id=row["task_id"],
        invoice_id=row["invoice_id"],
        idempotency_key=str(row["idempotency_key"]),
        comment=str(row["comment"]) if row["comment"] is not None else None,
        metadata=dict(metadata or {}),
        created_at=row["created_at"],
    )


__all__ = ("MeowWalletRepository",)
