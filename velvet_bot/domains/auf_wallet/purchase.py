from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Any, Mapping
from uuid import UUID, uuid4

from velvet_bot.database import Database
from velvet_bot.domains.auf_runtime import AufRuntimeService
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID

from .models import AufWallet
from .service import AUF_PACKAGES
from .store import _ensure_wallet, _wallet_from_row


class AufInvoiceStatus(StrEnum):
    CREATED = "created"
    PAID = "paid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


@dataclass(frozen=True, slots=True)
class AufPurchaseInvoice:
    id: UUID
    public_code: str
    workspace_id: int
    package_auf: int
    package_units: int
    package_price_usd: Decimal
    billing_currency: str
    locked_exchange_rate: Decimal
    final_local_amount: Decimal
    payment_method: str
    external_payment_id: str | None
    status: AufInvoiceStatus
    created_by_user_id: int
    confirmed_by_user_id: int | None
    expires_at: datetime
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AufReconciliationIssue:
    code: str
    workspace_id: int | None
    reference: str
    details: str


class AufInvoiceError(RuntimeError):
    pass


class AufPurchaseRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def create_invoice(
        self,
        *,
        workspace_id: int,
        package_auf: int,
        actor_user_id: int,
        idempotency_key: str,
        lifetime_hours: int = 24,
    ) -> AufPurchaseInvoice:
        amount = int(package_auf)
        if amount not in AUF_PACKAGES:
            raise ValueError("Неизвестный пакет Ауф.")
        key = _idempotency_key(idempotency_key)
        async with self._database.acquire() as connection:
            async with connection.transaction():
                existing = await connection.fetchrow(
                    """
                    SELECT * FROM auf_purchase_invoices
                    WHERE idempotency_key = $1::VARCHAR
                    """,
                    key,
                )
                if existing is not None:
                    return _invoice_from_row(existing)

                settings = await connection.fetchrow(
                    """
                    SELECT retail_auf_usd, billing_usd_to_rub
                    FROM auf_economy_settings
                    WHERE singleton_id = 1
                    """
                )
                if settings is None:
                    raise RuntimeError("Настройки экономики Ауф не инициализированы.")
                retail = Decimal(settings["retail_auf_usd"])
                rate = Decimal(settings["billing_usd_to_rub"])
                usd = (Decimal(amount) * retail).quantize(Decimal("0.01"))
                local = _round_rub(usd * rate)
                invoice_id = uuid4()
                public_code = _public_code(invoice_id)
                expires_at = datetime.now(timezone.utc) + timedelta(
                    hours=max(1, min(int(lifetime_hours), 168))
                )
                row = await connection.fetchrow(
                    """
                    INSERT INTO auf_purchase_invoices (
                        id, public_code, workspace_id,
                        package_auf, package_units, package_price_usd,
                        billing_currency, locked_exchange_rate, final_local_amount,
                        payment_method, status, idempotency_key,
                        created_by_user_id, expires_at
                    )
                    VALUES (
                        $1::UUID, $2::VARCHAR, $3::BIGINT,
                        $4::INTEGER, $5::BIGINT, $6::NUMERIC,
                        'RUB', $7::NUMERIC, $8::NUMERIC,
                        'manual', 'created', $9::VARCHAR,
                        $10::BIGINT, $11::TIMESTAMPTZ
                    )
                    RETURNING *
                    """,
                    invoice_id,
                    public_code,
                    int(workspace_id),
                    amount,
                    amount * 10_000,
                    usd,
                    rate,
                    local,
                    key,
                    int(actor_user_id),
                    expires_at,
                )
        if row is None:
            raise RuntimeError("Не удалось создать счёт на покупку Ауф.")
        return _invoice_from_row(row)

    async def recent_invoices(
        self,
        *,
        workspace_id: int,
        limit: int = 5,
    ) -> tuple[AufPurchaseInvoice, ...]:
        safe_limit = max(1, min(int(limit), 20))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT * FROM auf_purchase_invoices
                WHERE workspace_id = $1::BIGINT
                ORDER BY created_at DESC, id DESC
                LIMIT $2::INTEGER
                """,
                int(workspace_id),
                safe_limit,
            )
        return tuple(_invoice_from_row(row) for row in rows)

    async def invoice_by_code(self, public_code: str) -> AufPurchaseInvoice | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT * FROM auf_purchase_invoices WHERE public_code = $1::VARCHAR",
                _normalize_code(public_code),
            )
        return _invoice_from_row(row) if row is not None else None

    async def confirm_paid(
        self,
        *,
        public_code: str,
        actor_user_id: int,
        external_payment_id: str | None = None,
    ) -> tuple[AufPurchaseInvoice, AufWallet]:
        code = _normalize_code(public_code)
        external_id = _optional_text(external_payment_id)
        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT * FROM auf_purchase_invoices
                    WHERE public_code = $1::VARCHAR
                    FOR UPDATE
                    """,
                    code,
                )
                if row is None:
                    raise AufInvoiceError("Счёт Ауф не найден.")
                invoice = _invoice_from_row(row)
                wallet_row = await _ensure_wallet(
                    connection,
                    workspace_id=invoice.workspace_id,
                    for_update=True,
                )
                if invoice.status is AufInvoiceStatus.PAID:
                    return invoice, _wallet_from_row(wallet_row)
                if invoice.status is not AufInvoiceStatus.CREATED:
                    raise AufInvoiceError(
                        f"Нельзя подтвердить счёт со статусом {invoice.status.value}."
                    )
                if invoice.expires_at <= datetime.now(timezone.utc):
                    await connection.execute(
                        """
                        UPDATE auf_purchase_invoices
                        SET status = 'expired', updated_at = NOW()
                        WHERE id = $1::UUID
                        """,
                        invoice.id,
                    )
                    raise AufInvoiceError("Срок действия счёта Ауф истёк.")

                updated_wallet = await connection.fetchrow(
                    """
                    UPDATE auf_wallets
                    SET available_units = available_units + $2::BIGINT,
                        updated_at = NOW()
                    WHERE workspace_id = $1::BIGINT
                    RETURNING workspace_id, available_units, reserved_units,
                              status, created_at, updated_at
                    """,
                    invoice.workspace_id,
                    invoice.package_units,
                )
                if updated_wallet is None:
                    raise RuntimeError("Кошелёк Ауф исчез при подтверждении оплаты.")

                await connection.execute(
                    """
                    INSERT INTO auf_wallet_entries (
                        workspace_id, operation_type, amount_units,
                        available_after_units, reserved_after_units,
                        actor_user_id, invoice_id, idempotency_key,
                        comment, metadata
                    )
                    VALUES (
                        $1::BIGINT, 'purchase', $2::BIGINT,
                        $3::BIGINT, $4::BIGINT,
                        $5::BIGINT, $6::UUID, $7::VARCHAR,
                        $8::TEXT, $9::JSONB
                    )
                    ON CONFLICT (idempotency_key) DO NOTHING
                    """,
                    invoice.workspace_id,
                    invoice.package_units,
                    int(updated_wallet["available_units"]),
                    int(updated_wallet["reserved_units"]),
                    int(actor_user_id),
                    invoice.id,
                    f"invoice:{invoice.id}:purchase",
                    f"Оплата пакета {invoice.package_auf} Ауф подтверждена.",
                    json.dumps(
                        {
                            "invoice_code": invoice.public_code,
                            "package_price_usd": str(invoice.package_price_usd),
                            "billing_currency": invoice.billing_currency,
                            "locked_exchange_rate": str(invoice.locked_exchange_rate),
                            "final_local_amount": str(invoice.final_local_amount),
                            "external_payment_id": external_id,
                        },
                        ensure_ascii=False,
                    ),
                )
                paid_row = await connection.fetchrow(
                    """
                    UPDATE auf_purchase_invoices
                    SET status = 'paid',
                        external_payment_id = COALESCE($2::VARCHAR, external_payment_id),
                        confirmed_by_user_id = $3::BIGINT,
                        paid_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $1::UUID
                    RETURNING *
                    """,
                    invoice.id,
                    external_id,
                    int(actor_user_id),
                )
        if paid_row is None:
            raise RuntimeError("Не удалось подтвердить оплату счёта Ауф.")
        return _invoice_from_row(paid_row), _wallet_from_row(updated_wallet)

    async def cancel_invoice(
        self,
        *,
        public_code: str,
        workspace_id: int,
    ) -> AufPurchaseInvoice:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE auf_purchase_invoices
                SET status = 'cancelled', updated_at = NOW()
                WHERE public_code = $1::VARCHAR
                  AND workspace_id = $2::BIGINT
                  AND status = 'created'
                RETURNING *
                """,
                _normalize_code(public_code),
                int(workspace_id),
            )
        if row is None:
            existing = await self.invoice_by_code(public_code)
            if existing is None or existing.workspace_id != int(workspace_id):
                raise AufInvoiceError("Счёт Ауф не найден.")
            if existing.status is AufInvoiceStatus.CANCELLED:
                return existing
            raise AufInvoiceError(
                f"Нельзя отменить счёт со статусом {existing.status.value}."
            )
        return _invoice_from_row(row)

    async def expire_invoices(self) -> int:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE auf_purchase_invoices
                SET status = 'expired', updated_at = NOW()
                WHERE status = 'created' AND expires_at <= NOW()
                """
            )
        return int(result.rsplit(" ", 1)[-1])

    async def reconciliation_issues(
        self,
        *,
        limit: int = 50,
    ) -> tuple[AufReconciliationIssue, ...]:
        safe_limit = max(1, min(int(limit), 200))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                WITH issues AS (
                    SELECT
                        'orphan_reserved_charge'::VARCHAR AS code,
                        charge.workspace_id,
                        charge.task_id::TEXT AS reference,
                        'Резерв есть, а operational ai_task отсутствует.'::TEXT AS details
                    FROM auf_task_charges AS charge
                    LEFT JOIN ai_tasks AS task ON task.id = charge.task_id
                    WHERE charge.status = 'reserved' AND task.id IS NULL

                    UNION ALL

                    SELECT
                        'terminal_task_reserved'::VARCHAR,
                        charge.workspace_id,
                        charge.task_id::TEXT,
                        'Задача завершена, но charge остался reserved.'::TEXT
                    FROM auf_task_charges AS charge
                    JOIN ai_tasks AS task ON task.id = charge.task_id
                    WHERE charge.status = 'reserved'
                      AND task.status IN ('success', 'error', 'cancelled')

                    UNION ALL

                    SELECT
                        'reserved_balance_mismatch'::VARCHAR,
                        wallet.workspace_id,
                        wallet.workspace_id::TEXT,
                        'reserved_units кошелька не совпадает с суммой активных charge.'::TEXT
                    FROM auf_wallets AS wallet
                    LEFT JOIN (
                        SELECT workspace_id, COALESCE(SUM(reserved_units), 0) AS total
                        FROM auf_task_charges
                        WHERE status = 'reserved'
                        GROUP BY workspace_id
                    ) AS charge_total ON charge_total.workspace_id = wallet.workspace_id
                    WHERE wallet.reserved_units <> COALESCE(charge_total.total, 0)

                    UNION ALL

                    SELECT
                        'wallet_ledger_mismatch'::VARCHAR,
                        wallet.workspace_id,
                        wallet.workspace_id::TEXT,
                        'Текущий баланс кошелька не совпадает с последним ledger snapshot.'::TEXT
                    FROM auf_wallets AS wallet
                    JOIN LATERAL (
                        SELECT available_after_units, reserved_after_units
                        FROM auf_wallet_entries
                        WHERE workspace_id = wallet.workspace_id
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                    ) AS latest ON TRUE
                    WHERE wallet.available_units <> latest.available_after_units
                       OR wallet.reserved_units <> latest.reserved_after_units

                    UNION ALL

                    SELECT
                        'paid_invoice_without_ledger'::VARCHAR,
                        invoice.workspace_id,
                        invoice.public_code,
                        'Оплаченный счёт не имеет purchase-записи в журнале.'::TEXT
                    FROM auf_purchase_invoices AS invoice
                    LEFT JOIN auf_wallet_entries AS entry
                      ON entry.invoice_id = invoice.id
                     AND entry.operation_type = 'purchase'
                    WHERE invoice.status = 'paid' AND entry.id IS NULL

                    UNION ALL

                    SELECT
                        'purchase_ledger_without_paid_invoice'::VARCHAR,
                        entry.workspace_id,
                        COALESCE(invoice.public_code, entry.invoice_id::TEXT),
                        'Purchase-запись не связана с оплаченным счётом.'::TEXT
                    FROM auf_wallet_entries AS entry
                    LEFT JOIN auf_purchase_invoices AS invoice
                      ON invoice.id = entry.invoice_id
                    WHERE entry.operation_type = 'purchase'
                      AND (invoice.id IS NULL OR invoice.status <> 'paid')
                )
                SELECT code, workspace_id, reference, details
                FROM issues
                ORDER BY code, workspace_id NULLS LAST, reference
                LIMIT $1::INTEGER
                """,
                safe_limit,
            )
        return tuple(
            AufReconciliationIssue(
                code=str(row["code"]),
                workspace_id=(
                    int(row["workspace_id"])
                    if row["workspace_id"] is not None
                    else None
                ),
                reference=str(row["reference"]),
                details=str(row["details"]),
            )
            for row in rows
        )

    async def claim_reconciliation_notice(
        self,
        issues: tuple[AufReconciliationIssue, ...],
    ) -> bool:
        payload = [
            (item.code, item.workspace_id, item.reference, item.details)
            for item in issues
        ]
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE auf_reconciliation_state
                SET last_fingerprint = $1::VARCHAR,
                    last_sent_at = NOW(),
                    last_checked_at = NOW(),
                    updated_at = NOW()
                WHERE singleton_id = 1
                  AND (
                      last_fingerprint IS DISTINCT FROM $1::VARCHAR
                      OR last_sent_at IS NULL
                      OR last_sent_at < NOW() - INTERVAL '24 hours'
                  )
                """,
                fingerprint,
            )
        return result.endswith(" 1")

    async def mark_reconciliation_checked(self) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE auf_reconciliation_state
                SET last_checked_at = NOW(), updated_at = NOW()
                WHERE singleton_id = 1
                """
            )


class AufPurchaseService:
    def __init__(
        self,
        repository: AufPurchaseRepository,
        runtime_service: AufRuntimeService,
    ) -> None:
        self._repository = repository
        self._runtime = runtime_service

    async def create_invoice(
        self,
        *,
        workspace_id: int,
        package_auf: int,
        actor_user_id: int,
        idempotency_key: str,
    ) -> AufPurchaseInvoice:
        await self._runtime.require_workspace_access(
            workspace_id=int(workspace_id),
            actor_user_id=int(actor_user_id),
        )
        return await self._repository.create_invoice(
            workspace_id=int(workspace_id),
            package_auf=int(package_auf),
            actor_user_id=int(actor_user_id),
            idempotency_key=idempotency_key,
        )

    async def recent_invoices(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        limit: int = 5,
    ) -> tuple[AufPurchaseInvoice, ...]:
        await self._runtime.require_workspace_access(
            workspace_id=int(workspace_id),
            actor_user_id=int(actor_user_id),
        )
        return await self._repository.recent_invoices(
            workspace_id=int(workspace_id),
            limit=limit,
        )

    async def confirm_paid(
        self,
        *,
        public_code: str,
        actor_user_id: int,
    ) -> tuple[AufPurchaseInvoice, AufWallet]:
        self._require_global_owner(actor_user_id)
        return await self._repository.confirm_paid(
            public_code=public_code,
            actor_user_id=int(actor_user_id),
        )

    async def cancel_invoice(
        self,
        *,
        public_code: str,
        workspace_id: int,
        actor_user_id: int,
    ) -> AufPurchaseInvoice:
        await self._runtime.require_workspace_access(
            workspace_id=int(workspace_id),
            actor_user_id=int(actor_user_id),
        )
        return await self._repository.cancel_invoice(
            public_code=public_code,
            workspace_id=int(workspace_id),
        )

    @staticmethod
    def is_global_owner(user_id: int) -> bool:
        return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID

    def _require_global_owner(self, actor_user_id: int) -> None:
        if not self.is_global_owner(actor_user_id):
            raise PermissionError("Подтверждать оплату Ауф может только Стэл.")


def _invoice_from_row(row: Mapping[str, Any]) -> AufPurchaseInvoice:
    return AufPurchaseInvoice(
        id=row["id"],
        public_code=str(row["public_code"]),
        workspace_id=int(row["workspace_id"]),
        package_auf=int(row["package_auf"]),
        package_units=int(row["package_units"]),
        package_price_usd=Decimal(row["package_price_usd"]),
        billing_currency=str(row["billing_currency"]),
        locked_exchange_rate=Decimal(row["locked_exchange_rate"]),
        final_local_amount=Decimal(row["final_local_amount"]),
        payment_method=str(row["payment_method"]),
        external_payment_id=_optional_text(row["external_payment_id"]),
        status=AufInvoiceStatus(str(row["status"])),
        created_by_user_id=int(row["created_by_user_id"]),
        confirmed_by_user_id=(
            int(row["confirmed_by_user_id"])
            if row["confirmed_by_user_id"] is not None
            else None
        ),
        expires_at=row["expires_at"],
        paid_at=row["paid_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _public_code(invoice_id: UUID) -> str:
    return invoice_id.hex[:12].upper()


def _normalize_code(value: str) -> str:
    code = "".join(char for char in value.strip().upper() if char.isalnum())
    if not code or len(code) > 16:
        raise ValueError("Некорректный код счёта Ауф.")
    return code


def _idempotency_key(value: str) -> str:
    key = " ".join(value.split())
    if not key or len(key) > 160:
        raise ValueError("Некорректный idempotency key счёта Ауф.")
    return key


def _round_rub(value: Decimal) -> Decimal:
    return (
        (value / Decimal(10)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        * Decimal(10)
    ).quantize(Decimal("0.01"))


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


__all__ = (
    "AufInvoiceError",
    "AufInvoiceStatus",
    "AufPurchaseInvoice",
    "AufPurchaseRepository",
    "AufPurchaseService",
    "AufReconciliationIssue",
)
