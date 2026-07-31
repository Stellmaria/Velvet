from __future__ import annotations

import json
from collections.abc import Sequence

from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import (
    AITaskEnqueueResult,
    AITaskQueueService,
    AITaskRepository,
    AITaskRequest,
)
from velvet_bot.domains.media_generation import KIE_GENERATION_TASK_TYPE
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID

from .charged_queue_expected_quote import validate_expected_auf_quote
from .models import AUF_SCALE, AufInsufficientBalance, AufWalletFrozen
from .pricing import AufPriceQuote, quote_auf_payload


class AufChargedTaskQueueService(AITaskQueueService):
    """Atomically reserve whole velvets and enqueue paid Auf generation tasks."""

    def __init__(self, database: Database) -> None:
        repository = AITaskRepository(database)
        super().__init__(repository)
        self._database = database
        self._tasks = repository

    async def enqueue(self, request: AITaskRequest) -> AITaskEnqueueResult:
        if not _is_chargeable(request):
            return await super().enqueue(request)

        workspace_id = _workspace_id(request)
        async with self._database.acquire() as connection:
            async with connection.transaction():
                pricing_payload = dict(request.payload)
                pricing_payload["user_id"] = int(request.created_by or 0)
                quote = await quote_auf_payload(connection, pricing_payload)
                validate_expected_auf_quote(request.payload, quote)
                result = await self._tasks._enqueue_on_connection(connection, request)
                if not result.created:
                    return result
                await _reserve_charge(
                    connection,
                    workspace_id=workspace_id,
                    task_id=result.task.id,
                    actor_user_id=request.created_by,
                    quote=quote,
                )
                return result

    async def enqueue_many(
        self,
        requests: Sequence[AITaskRequest],
    ) -> tuple[AITaskEnqueueResult, ...]:
        # Each task has its own quote and reservation. A failure must not roll back
        # unrelated tasks that were already explicitly confirmed by the caller.
        return tuple([await self.enqueue(request) for request in requests])


def build_auf_charged_task_queue_service(
    *,
    database: Database,
) -> AufChargedTaskQueueService:
    return AufChargedTaskQueueService(database)


def _is_chargeable(request: AITaskRequest) -> bool:
    if request.task_type != KIE_GENERATION_TASK_TYPE:
        return False
    return int(request.created_by or 0) != GLOBAL_WORKSPACE_CREATOR_ID


def _workspace_id(request: AITaskRequest) -> int:
    try:
        workspace_id = int(str(request.payload.get("workspace_id") or "").strip())
    except (TypeError, ValueError) as error:
        raise ValueError("Для платной генерации не указано личное пространство.") from error
    if workspace_id <= 0:
        raise ValueError("Для платной генерации не указано личное пространство.")
    return workspace_id


async def _reserve_charge(
    connection,
    *,
    workspace_id: int,
    task_id,
    actor_user_id: int | None,
    quote: AufPriceQuote,
) -> None:
    if quote.quoted_units <= 0 or quote.quoted_units % AUF_SCALE != 0:
        raise RuntimeError("Списание генерации должно быть целым числом VL.")

    await connection.execute(
        """
        INSERT INTO auf_wallets (workspace_id)
        VALUES ($1::BIGINT)
        ON CONFLICT (workspace_id) DO NOTHING
        """,
        workspace_id,
    )
    wallet = await connection.fetchrow(
        """
        SELECT workspace_id, available_units, reserved_units, status
        FROM auf_wallets
        WHERE workspace_id = $1::BIGINT
        FOR UPDATE
        """,
        workspace_id,
    )
    if wallet is None:
        raise RuntimeError("Не удалось загрузить кошелёк Ауф для резервирования.")
    if str(wallet["status"]) != "active":
        raise AufWalletFrozen("Кошелёк Ауф этого пространства заморожен.")

    available = int(wallet["available_units"])
    if available < quote.quoted_units:
        raise AufInsufficientBalance(
            required_units=quote.quoted_units,
            available_units=available,
        )

    updated_wallet = await connection.fetchrow(
        """
        UPDATE auf_wallets
        SET available_units = available_units - $2::BIGINT,
            reserved_units = reserved_units + $2::BIGINT,
            updated_at = NOW()
        WHERE workspace_id = $1::BIGINT
        RETURNING available_units, reserved_units
        """,
        workspace_id,
        quote.quoted_units,
    )
    if updated_wallet is None:
        raise RuntimeError("Кошелёк Ауф исчез во время резервирования.")

    await connection.execute(
        """
        INSERT INTO auf_task_charges (
            task_id, workspace_id, price_version_id,
            quoted_units, reserved_units, provider_cost_usd, status
        )
        VALUES (
            $1::UUID, $2::BIGINT, $3::BIGINT,
            $4::BIGINT, $4::BIGINT, $5::NUMERIC, 'reserved'
        )
        """,
        task_id,
        workspace_id,
        quote.price_version_id,
        quote.quoted_units,
        quote.provider_cost_usd,
    )
    await connection.execute(
        """
        INSERT INTO auf_wallet_entries (
            workspace_id, operation_type, amount_units,
            available_after_units, reserved_after_units,
            actor_user_id, task_id, idempotency_key, comment, metadata
        )
        VALUES (
            $1::BIGINT, 'reserve', $2::BIGINT,
            $3::BIGINT, $4::BIGINT,
            $5::BIGINT, $6::UUID, $7::VARCHAR, $8::TEXT, $9::JSONB
        )
        """,
        workspace_id,
        -quote.quoted_units,
        int(updated_wallet["available_units"]),
        int(updated_wallet["reserved_units"]),
        int(actor_user_id) if actor_user_id is not None else None,
        task_id,
        f"task:{task_id}:reserve",
        "Резерв перед запуском генерации.",
        json.dumps(
            {
                "price_version": quote.version_key,
                "model": quote.model_alias,
                "resolution": quote.resolution,
                "audio": quote.audio,
                "duration_seconds": quote.duration_seconds,
                "reference_count": quote.reference_count,
                "provider_cost_usd": str(quote.provider_cost_usd),
                "global_markup_percent": str(quote.global_markup_percent),
                "user_markup_override_percent": (
                    str(quote.user_markup_override_percent)
                    if quote.user_markup_override_percent is not None
                    else None
                ),
                "markup_percent": str(quote.markup_percent),
                "quality_surcharge_velvets": quote.quality_surcharge_velvets,
                "target_retail_usd": str(quote.target_retail_usd),
                "minimum_revenue_usd": str(quote.minimum_revenue_usd),
                "billing_usd_to_rub": str(quote.billing_usd_to_rub),
                "billing_usd_to_byn": str(quote.billing_usd_to_byn),
                "whole_velvets": quote.quoted_units // AUF_SCALE,
            },
            ensure_ascii=False,
        ),
    )


__all__ = (
    "AufChargedTaskQueueService",
    "build_auf_charged_task_queue_service",
)
