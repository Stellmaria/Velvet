from __future__ import annotations

from uuid import UUID

from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID

from .models import (
    AufCancellationResult,
    AufProvider,
    AufProviderSnapshot,
    AufRuntimeSettings,
    WorkspaceAufSettings,
)
from .store import AufRuntimeRepository

# Persisted before the public rename. Keep the storage key stable until a dedicated
# database migration moves existing workspace module rows to ``auf``.
_LEGACY_AUF_MODULE_KEY = "meow"


class AufRuntimeAccessError(PermissionError):
    pass


class AufRuntimeService:
    def __init__(self, repository: AufRuntimeRepository) -> None:
        self._repository = repository

    @staticmethod
    def is_global_owner(user_id: int) -> bool:
        return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID

    async def runtime_settings(self, *, actor_user_id: int) -> AufRuntimeSettings:
        self._require_global_owner(actor_user_id)
        return await self._repository.runtime_settings()

    async def set_provider_limit(
        self,
        *,
        actor_user_id: int,
        provider: AufProvider,
        limit: int,
    ) -> AufRuntimeSettings:
        self._require_global_owner(actor_user_id)
        if not 1 <= int(limit) <= 100:
            raise ValueError("Глобальный лимит провайдера должен быть от 1 до 100.")
        return await self._repository.set_provider_limit(
            provider=provider,
            limit=int(limit),
            updated_by_user_id=int(actor_user_id),
        )

    async def confirm_runtime_settings(
        self,
        *,
        actor_user_id: int,
    ) -> AufRuntimeSettings:
        self._require_global_owner(actor_user_id)
        return await self._repository.confirm_runtime_settings(
            updated_by_user_id=int(actor_user_id)
        )

    async def claim_setup_notice(self) -> bool:
        return await self._repository.claim_setup_notice()

    async def workspace_settings(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
    ) -> WorkspaceAufSettings:
        await self.require_workspace_access(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )
        return await self._repository.workspace_settings(workspace_id)

    async def set_workspace_limit(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        limit: int,
    ) -> WorkspaceAufSettings:
        await self.require_workspace_access(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )
        if not 1 <= int(limit) <= 20:
            raise ValueError("Лимит пространства должен быть от 1 до 20.")
        return await self._repository.set_workspace_limit(
            workspace_id=workspace_id,
            limit=int(limit),
            updated_by_user_id=int(actor_user_id),
        )

    async def require_workspace_access(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
    ) -> None:
        allowed = await self._repository.can_use_auf(
            workspace_id=workspace_id,
            user_id=actor_user_id,
            global_owner=self.is_global_owner(actor_user_id),
        )
        if not allowed:
            raise AufRuntimeAccessError(
                "Модуль Ауф не разрешён Стэл, выключен владельцем или недоступен вашей роли."
            )

    async def is_workspace_owner(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
    ) -> bool:
        return await self._repository.is_workspace_owner(
            workspace_id=workspace_id,
            user_id=actor_user_id,
        )

    async def hidden_modules(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
    ) -> frozenset[str]:
        return await self._repository.hidden_modules_for_user(
            workspace_id=workspace_id,
            user_id=actor_user_id,
        )

    async def module_is_visible(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        module_key: str = _LEGACY_AUF_MODULE_KEY,
    ) -> bool:
        return await self._repository.module_is_visible(
            workspace_id=workspace_id,
            user_id=actor_user_id,
            module_key=module_key,
        )

    async def set_module_visible(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        is_visible: bool,
        module_key: str = _LEGACY_AUF_MODULE_KEY,
    ) -> bool:
        if not await self._repository.is_workspace_owner(
            workspace_id=workspace_id,
            user_id=actor_user_id,
        ):
            raise AufRuntimeAccessError(
                "Настраивать отображение Ауф может только владелец пространства."
            )
        return await self._repository.set_module_visible(
            workspace_id=workspace_id,
            user_id=actor_user_id,
            module_key=module_key,
            is_visible=is_visible,
        )

    async def provider_snapshots(
        self,
        *,
        actor_user_id: int,
    ) -> tuple[AufProviderSnapshot, AufProviderSnapshot]:
        self._require_global_owner(actor_user_id)
        return (
            await self._repository.provider_snapshot(AufProvider.KIE),
            await self._repository.provider_snapshot(AufProvider.GRS),
        )

    async def request_cancellation(
        self,
        *,
        task_id: UUID,
        actor_user_id: int,
    ) -> AufCancellationResult | None:
        return await self._repository.request_task_cancellation(
            task_id=task_id,
            requested_by_user_id=actor_user_id,
            global_owner=self.is_global_owner(actor_user_id),
        )

    async def cancellation_requested(self, task_id: UUID) -> bool:
        return await self._repository.cancellation_requested(task_id)

    @staticmethod
    def _require_global_owner(actor_user_id: int) -> None:
        if not AufRuntimeService.is_global_owner(actor_user_id):
            raise AufRuntimeAccessError("Эта настройка доступна только Стэл.")


__all__ = (
    "AufRuntimeAccessError",
    "AufRuntimeService",
)
