from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4

from velvet_bot.domains.auf_runtime import AufRuntimeService
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID

from .economics import AufEconomicsRepository
from .models import (
    AufEconomySettings,
    AufMarginSummary,
    AufWallet,
    AufWalletOperation,
    AufWalletOverview,
    AufWalletStatus,
    auf_to_units,
)
from .package_pricing import active_package_prices
from .store import AufWalletRepository

AUF_PACKAGES = (20, 50, 75, 100, 150, 250)


@dataclass(frozen=True, slots=True)
class AufPackageQuote:
    amount_auf: int
    price_usd: Decimal
    price_rub: Decimal
    price_byn: Decimal


class AufWalletAccessError(PermissionError):
    pass


class AufWalletService:
    def __init__(
        self,
        repository: AufWalletRepository,
        runtime_service: AufRuntimeService,
    ) -> None:
        self._repository = repository
        self._runtime = runtime_service
        self._economics = AufEconomicsRepository(repository._database)

    @staticmethod
    def is_global_owner(user_id: int) -> bool:
        return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID

    async def overview(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        history_limit: int = 10,
    ) -> AufWalletOverview:
        await self._require_workspace_access(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )
        return await self._repository.overview(
            int(workspace_id),
            history_limit=history_limit,
        )

    async def economy_settings(self, *, actor_user_id: int) -> AufEconomySettings:
        self._require_global_owner(actor_user_id)
        return await self._repository.economy_settings()

    async def margin_summary(
        self,
        *,
        actor_user_id: int,
        days: int = 30,
    ) -> AufMarginSummary:
        self._require_global_owner(actor_user_id)
        return await self._economics.margin_summary(days=days)

    async def record_actual_provider_cost(
        self,
        *,
        task_id: UUID,
        actual_provider_cost_usd: Decimal,
        actor_user_id: int,
    ) -> None:
        self._require_global_owner(actor_user_id)
        await self._economics.record_actual_provider_cost(
            task_id=task_id,
            actual_provider_cost_usd=actual_provider_cost_usd,
        )

    async def package_quotes(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
    ) -> tuple[AufPackageQuote, ...]:
        await self._require_workspace_access(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )
        settings = await self._repository.economy_settings()
        fixed_prices = await active_package_prices(
            getattr(self._repository, "_database", None)
        )
        quotes: list[AufPackageQuote] = []
        for amount in AUF_PACKAGES:
            fixed_rub = fixed_prices.get(amount)
            if fixed_rub is None:
                quotes.append(_package_quote(amount, settings))
                continue
            price_usd = (fixed_rub / settings.billing_usd_to_rub).quantize(
                Decimal("0.01")
            )
            quotes.append(
                AufPackageQuote(
                    amount_auf=amount,
                    price_usd=price_usd,
                    price_rub=fixed_rub,
                    price_byn=(price_usd * settings.billing_usd_to_byn).quantize(
                        Decimal("0.01")
                    ),
                )
            )
        return tuple(quotes)

    async def grant(
        self,
        *,
        workspace_id: int,
        amount_auf: Decimal | str | int,
        actor_user_id: int,
        comment: str,
        idempotency_key: str | None = None,
    ) -> AufWallet:
        self._require_global_owner(actor_user_id)
        units = auf_to_units(amount_auf)
        if units <= 0:
            raise ValueError("Начисление должно быть больше нуля.")
        return await self._repository.change_available(
            workspace_id=int(workspace_id),
            amount_units=units,
            operation_type=AufWalletOperation.GRANT,
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
    ) -> AufWallet:
        self._require_global_owner(actor_user_id)
        units = auf_to_units(amount_auf)
        if units <= 0:
            raise ValueError("Списание должно быть больше нуля.")
        if not comment.strip():
            raise ValueError("Для ручного списания обязателен комментарий.")
        return await self._repository.change_available(
            workspace_id=int(workspace_id),
            amount_units=-units,
            operation_type=AufWalletOperation.MANUAL_DEBIT,
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
    ) -> AufWallet:
        self._require_global_owner(actor_user_id)
        return await self._repository.set_status(
            workspace_id=int(workspace_id),
            status=(
                AufWalletStatus.FROZEN if frozen else AufWalletStatus.ACTIVE
            ),
        )

    async def update_economy_settings(
        self,
        *,
        provider_auf_usd: Decimal,
        retail_auf_usd: Decimal,
        billing_usd_to_rub: Decimal,
        billing_usd_to_byn: Decimal,
        retail_markup_percent: Decimal,
        actor_user_id: int,
    ) -> AufEconomySettings:
        self._require_global_owner(actor_user_id)
        if provider_auf_usd <= 0:
            raise ValueError("Покрытие API одного Ауф должно быть больше нуля.")
        if retail_auf_usd < provider_auf_usd:
            raise ValueError("Розничная цена Ауф не может быть ниже покрытия API.")
        if billing_usd_to_rub <= 0:
            raise ValueError("Курс USD/RUB должен быть больше нуля.")
        if billing_usd_to_byn <= 0:
            raise ValueError("Курс USD/BYN должен быть больше нуля.")
        if retail_markup_percent < 0 or retail_markup_percent > 1000:
            raise ValueError("Наценка должна быть от 0 до 1000 процентов.")
        return await self._repository.update_economy_settings(
            provider_auf_usd=provider_auf_usd,
            retail_auf_usd=retail_auf_usd,
            billing_usd_to_rub=billing_usd_to_rub,
            billing_usd_to_byn=billing_usd_to_byn,
            retail_markup_percent=retail_markup_percent,
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
            raise AufWalletAccessError(
                "Управление экономикой Ауф доступно только Стэл."
            )


def _package_quote(
    amount_auf: int,
    settings: AufEconomySettings,
) -> AufPackageQuote:
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
    return AufPackageQuote(
        amount_auf=amount_auf,
        price_usd=usd,
        price_rub=rub,
        price_byn=(usd * settings.billing_usd_to_byn).quantize(Decimal("0.01")),
    )


__all__ = (
    "AUF_PACKAGES",
    "AufPackageQuote",
    "AufWalletAccessError",
    "AufWalletService",
)
