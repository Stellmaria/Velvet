from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from velvet_bot.domains.meow_runtime import MeowRuntimeService
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID

from .models import (
    MeowEconomySettings,
    MeowWallet,
    MeowWalletOperation,
    MeowWalletOverview,
    MeowWalletStatus,
    auf_to_units,
)
from .store import MeowWalletRepository

AUF_PACKAGES = (40, 100, 250, 500, 1_000, 2_500)


@dataclass(frozen=True, slots=True)
class MeowAufPackageQuote:
    amount_auf: int
    price_usd: Decimal
    price_rub: Decimal


class MeowWalletAccessError(PermissionError):
    pass


class MeowWalletService:
    def __init__(
        self,
        repository: MeowWalletRepository,
        runtime_service: MeowRuntimeService,
    ) -> None:
        self._repository = repository
        self._runtime = runtime_service

    @staticmethod
    def is_global_owner(user_id: int) -> bool:
        return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID

    async def overview(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        history_limit: int = 10,
    ) -> MeowWalletOverview:
        await self._require_workspace_access(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )
        return await self._repository.overview(
            int(workspace_id),
            history_limit=history_limit,
        )

    async def economy_settings(self, *, actor_user_id: int) -> MeowEconomySettings:
        self._require_global_owner(actor_user_id)
        return await self._repository.economy_settings()

    async def package_quotes(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
    ) -> tuple[MeowAufPackageQuote, ...]:
        await self._require_workspace_access(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )
        settings = await self._repository.economy_settings()
        return tuple(_package_quote(amount, settings) for amount in AUF_PACKAGES)

    async def grant(
        self,
        *,
        workspace_id: int,
        amount_auf: Decimal | str | int,
        actor_user_id: int,
        comment: str,
        idempotency_key: str | None = None,
    ) -> MeowWallet:
        self._require_global_owner(actor_user_id)
        units = auf_to_units(amount_auf)
        if units <= 0:
            raise ValueError("Начисление должно быть больше нуля.")
        return await self._repository.change_available(
            workspace_id=int(workspace_id),
            amount_units=units,
            operation_type=MeowWalletOperation.GRANT,
            idempotency_key=(
                idempotency_key
                or f"grant:{workspace_id}:{actor_user_id}:{uuid4()}"
            ),
            actor_user_id=int(actor_user_id),
            comment=comment,
        )

    async def manual_debit(
        self,
        *,
        workspace_id: int,
        amount_auf: Decimal | str | int,
        actor_user_id: int,
        comment: str,
        idempotency_key: str | None = None,
    ) -> MeowWallet:
        self._require_global_owner(actor_user_id)
        units = auf_to_units(amount_auf)
        if units <= 0:
            raise ValueError("Списание должно быть больше нуля.")
        if not comment.strip():
            raise ValueError("Для ручного списания обязателен комментарий.")
        return await self._repository.change_available(
            workspace_id=int(workspace_id),
            amount_units=-units,
            operation_type=MeowWalletOperation.MANUAL_DEBIT,
            idempotency_key=(
                idempotency_key
                or f"manual-debit:{workspace_id}:{actor_user_id}:{uuid4()}"
            ),
            actor_user_id=int(actor_user_id),
            comment=comment,
        )

    async def set_frozen(
        self,
        *,
        workspace_id: int,
        frozen: bool,
        actor_user_id: int,
    ) -> MeowWallet:
        self._require_global_owner(actor_user_id)
        return await self._repository.set_status(
            workspace_id=int(workspace_id),
            status=(
                MeowWalletStatus.FROZEN if frozen else MeowWalletStatus.ACTIVE
            ),
        )

    async def update_economy_settings(
        self,
        *,
        provider_auf_usd: Decimal,
        retail_auf_usd: Decimal,
        billing_usd_to_rub: Decimal,
        actor_user_id: int,
    ) -> MeowEconomySettings:
        self._require_global_owner(actor_user_id)
        if provider_auf_usd <= 0:
            raise ValueError("Покрытие API одного Ауф должно быть больше нуля.")
        if retail_auf_usd < provider_auf_usd:
            raise ValueError("Розничная цена Ауф не может быть ниже покрытия API.")
        if billing_usd_to_rub <= 0:
            raise ValueError("Курс USD/RUB должен быть больше нуля.")
        return await self._repository.update_economy_settings(
            provider_auf_usd=provider_auf_usd,
            retail_auf_usd=retail_auf_usd,
            billing_usd_to_rub=billing_usd_to_rub,
            updated_by_user_id=int(actor_user_id),
        )

    async def _require_workspace_access(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
    ) -> None:
        await self._runtime.require_workspace_access(
            workspace_id=int(workspace_id),
            actor_user_id=int(actor_user_id),
        )

    def _require_global_owner(self, actor_user_id: int) -> None:
        if not self.is_global_owner(actor_user_id):
            raise MeowWalletAccessError(
                "Управление экономикой Ауф доступно только Стэл."
            )


def _package_quote(
    amount_auf: int,
    settings: MeowEconomySettings,
) -> MeowAufPackageQuote:
    usd = (Decimal(amount_auf) * settings.retail_auf_usd).quantize(Decimal("0.01"))
    raw_rub = usd * settings.billing_usd_to_rub
    rounding_step = Decimal(100) if raw_rub >= Decimal(1000) else Decimal(10)
    rub = (
        (raw_rub / rounding_step).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
        * rounding_step
    )
    return MeowAufPackageQuote(
        amount_auf=amount_auf,
        price_usd=usd,
        price_rub=rub,
    )


__all__ = (
    "AUF_PACKAGES",
    "MeowAufPackageQuote",
    "MeowWalletAccessError",
    "MeowWalletService",
)
