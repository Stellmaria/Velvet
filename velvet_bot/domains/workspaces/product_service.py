from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from velvet_bot.domains.characters.constants import (
    CATEGORY_EMOJI,
    CATEGORY_LABELS,
    CATEGORY_ORDER,
)
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID, Workspace
from velvet_bot.domains.workspaces.product_models import (
    DEFAULT_PERSONAL_MODULE_KEYS,
    GLOBAL_WORKSPACE_CREATOR_ID,
    WORKSPACE_MODULE_KEYS,
    WorkspaceCategory,
    WorkspaceCreationGrant,
    WorkspaceModuleKey,
    WorkspaceModuleSetting,
    WorkspaceStory,
    WorkspaceUniverse,
)
from velvet_bot.domains.workspaces.product_repository import WorkspaceProductRepository
from velvet_bot.domains.workspaces.repository import WorkspaceRepository
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService

_KEY_RE = re.compile(r"[^a-z0-9_-]+")


class WorkspaceCreationAccessError(PermissionError):
    pass


class WorkspaceModuleAccessError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class WorkspaceStartState:
    can_create: bool
    owned_workspaces: tuple[Workspace, ...]
    public_workspaces: tuple[Workspace, ...]


def normalize_taxonomy_key(value: str) -> str:
    cleaned = _KEY_RE.sub("-", value.strip().casefold()).strip("-_")
    if not cleaned:
        raise ValueError("Ключ должен содержать латинские буквы или цифры.")
    if len(cleaned) > 64:
        raise ValueError("Ключ не должен быть длиннее 64 символов.")
    return cleaned


def normalize_taxonomy_label(value: str, *, limit: int = 96) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Название не может быть пустым.")
    if len(cleaned) > limit:
        raise ValueError(f"Название не должно быть длиннее {limit} символов.")
    return cleaned


def normalize_emoji(value: str | None, *, fallback: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return fallback
    if len(cleaned) > 16:
        raise ValueError("Emoji или значок слишком длинный.")
    return cleaned


class WorkspaceProductService:
    """Rules for gated personal archives, modules and custom taxonomy."""

    def __init__(
        self,
        *,
        product_repository: WorkspaceProductRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self._product = product_repository
        self._workspaces = workspace_repository
        self._workspace_service = WorkspaceService(workspace_repository)

    @staticmethod
    def _require_global_creator(actor_user_id: int) -> None:
        if int(actor_user_id) != GLOBAL_WORKSPACE_CREATOR_ID:
            raise WorkspaceCreationAccessError(
                "Только Стэл может выдавать право на создание личного архива."
            )

    async def grant_creation_access(
        self,
        *,
        actor_user_id: int,
        user_id: int,
        allowed_modules: tuple[WorkspaceModuleKey, ...] = DEFAULT_PERSONAL_MODULE_KEYS,
        max_workspaces: int = 1,
    ) -> WorkspaceCreationGrant:
        self._require_global_creator(actor_user_id)
        if int(user_id) <= 0:
            raise ValueError("Telegram user ID должен быть положительным числом.")
        modules = tuple(dict.fromkeys(allowed_modules))
        if not modules or any(item not in WORKSPACE_MODULE_KEYS for item in modules):
            raise ValueError("Список модулей содержит неизвестное значение.")
        if max_workspaces < 1 or max_workspaces > 10:
            raise ValueError("Можно разрешить от 1 до 10 пространств.")
        return await self._product.upsert_creation_grant(
            user_id=int(user_id),
            granted_by_user_id=int(actor_user_id),
            allowed_modules=modules,
            max_workspaces=max_workspaces,
        )

    async def revoke_creation_access(
        self,
        *,
        actor_user_id: int,
        user_id: int,
    ) -> bool:
        self._require_global_creator(actor_user_id)
        return await self._product.revoke_creation_grant(int(user_id))

    async def can_create_workspace(self, user_id: int) -> bool:
        grant = await self._product.get_creation_grant(int(user_id))
        if grant is None or not grant.is_active:
            return False
        owned = await self._product.count_owned_personal_workspaces(int(user_id))
        return owned < grant.max_workspaces

    async def get_start_state(self, user_id: int) -> WorkspaceStartState:
        return WorkspaceStartState(
            can_create=await self.can_create_workspace(int(user_id)),
            owned_workspaces=await self._product.list_owned_personal_workspaces(int(user_id)),
            public_workspaces=await self._product.list_public_workspaces(),
        )

    async def create_personal_workspace(
        self,
        *,
        owner_user_id: int,
        name: str,
    ) -> Workspace:
        grant = await self._product.get_creation_grant(int(owner_user_id))
        if grant is None or not grant.is_active:
            raise WorkspaceCreationAccessError(
                "Стэл ещё не выдала вам право создать личный архив."
            )
        owned = await self._product.count_owned_personal_workspaces(int(owner_user_id))
        if owned >= grant.max_workspaces:
            raise WorkspaceCreationAccessError("Разрешённое количество архивов уже создано.")
        workspace = await self._workspace_service.create_personal_workspace(
            name=name,
            slug=f"user-{int(owner_user_id)}-{uuid4().hex[:12]}",
            owner_user_id=int(owner_user_id),
        )
        await self._product.initialize_modules(
            workspace_id=workspace.id,
            allowed_modules=grant.allowed_modules,
            updated_by_user_id=grant.granted_by_user_id,
        )
        for index, key in enumerate(CATEGORY_ORDER, start=1):
            await self._product.upsert_category(
                workspace_id=workspace.id,
                key=key,
                label=CATEGORY_LABELS[key],
                emoji=CATEGORY_EMOJI[key],
                created_by_user_id=int(owner_user_id),
            )
        settings = await self._workspaces.get_settings(workspace.id)
        if settings is None or settings.public_archive_enabled:
            raise RuntimeError("Новый личный архив должен создаваться приватным.")
        return workspace

    async def list_public_workspaces(self) -> tuple[Workspace, ...]:
        return await self._product.list_public_workspaces()

    async def select_public_workspace(
        self,
        *,
        user_id: int,
        workspace_id: int,
    ) -> bool:
        return await self._product.set_public_browse_workspace(
            user_id=int(user_id),
            workspace_id=int(workspace_id),
        )

    async def public_workspace_id_for_user(self, user_id: int) -> int:
        return await self._product.get_public_browse_workspace_id(int(user_id))

    async def set_public_archive_enabled(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        enabled: bool,
        global_owner: bool = False,
    ) -> None:
        await self._workspace_service.require_role(
            workspace_id=int(workspace_id),
            user_id=int(actor_user_id),
            minimum_role="owner",
            global_owner=global_owner,
        )
        settings = await self._workspaces.get_settings(int(workspace_id))
        if settings is None:
            raise ValueError("Настройки пространства не найдены.")
        await self._workspace_service.update_settings(
            workspace_id=int(workspace_id),
            actor_user_id=int(actor_user_id),
            timezone=settings.timezone,
            public_archive_enabled=bool(enabled),
            downloads_mode=settings.downloads_mode,
            qwen_enabled=settings.qwen_enabled,
            global_owner=global_owner,
        )

    async def list_modules(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        global_owner: bool = False,
    ) -> tuple[WorkspaceModuleSetting, ...]:
        await self._workspace_service.require_role(
            workspace_id=int(workspace_id),
            user_id=int(actor_user_id),
            minimum_role="owner",
            global_owner=global_owner,
        )
        return await self._product.list_modules(int(workspace_id))

    async def set_module_allowed(
        self,
        *,
        actor_user_id: int,
        workspace_id: int,
        module_key: WorkspaceModuleKey,
        is_allowed: bool,
    ) -> WorkspaceModuleSetting:
        self._require_global_creator(actor_user_id)
        if module_key not in WORKSPACE_MODULE_KEYS:
            raise ValueError("Неизвестный модуль.")
        workspace = await self._workspaces.get(int(workspace_id))
        if workspace is None:
            raise ValueError("Пространство не найдено.")
        return await self._product.set_module_policy(
            workspace_id=int(workspace_id),
            module_key=module_key,
            is_allowed=bool(is_allowed),
            updated_by_user_id=int(actor_user_id),
        )

    async def set_module_enabled(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        module_key: WorkspaceModuleKey,
        is_enabled: bool,
        global_owner: bool = False,
    ) -> WorkspaceModuleSetting:
        await self._workspace_service.require_role(
            workspace_id=int(workspace_id),
            user_id=int(actor_user_id),
            minimum_role="owner",
            global_owner=global_owner,
        )
        if module_key not in WORKSPACE_MODULE_KEYS:
            raise ValueError("Неизвестный модуль.")
        setting = await self._product.set_module_enabled(
            workspace_id=int(workspace_id),
            module_key=module_key,
            is_enabled=bool(is_enabled),
            updated_by_user_id=int(actor_user_id),
        )
        if setting is None:
            raise WorkspaceModuleAccessError(
                "Этот модуль не разрешён создателем бота."
            )
        return setting

    async def is_module_enabled(
        self,
        *,
        workspace_id: int,
        module_key: WorkspaceModuleKey,
    ) -> bool:
        """Return the effective module state after caller access was verified."""
        if module_key not in WORKSPACE_MODULE_KEYS:
            raise ValueError("Неизвестный модуль.")
        modules = await self._product.list_modules(int(workspace_id))
        return any(
            item.module_key == module_key and item.is_allowed and item.is_enabled
            for item in modules
        )

    async def _require_taxonomy_access(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        global_owner: bool,
    ) -> None:
        await self._workspace_service.require_role(
            workspace_id=int(workspace_id),
            user_id=int(actor_user_id),
            minimum_role="editor",
            global_owner=global_owner,
        )
        settings = {
            item.module_key: item
            for item in await self._product.list_modules(int(workspace_id))
        }
        taxonomy = settings.get("taxonomy")
        if taxonomy is None or not taxonomy.is_allowed or not taxonomy.is_enabled:
            raise WorkspaceModuleAccessError("Модуль категорий и вселенных выключен.")

    async def create_category(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        key: str,
        label: str,
        emoji: str | None = None,
        global_owner: bool = False,
    ) -> WorkspaceCategory:
        await self._require_taxonomy_access(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            global_owner=global_owner,
        )
        return await self._product.upsert_category(
            workspace_id=int(workspace_id),
            key=normalize_taxonomy_key(key),
            label=normalize_taxonomy_label(label),
            emoji=normalize_emoji(emoji, fallback="📁"),
            created_by_user_id=int(actor_user_id),
        )

    async def create_universe(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        key: str,
        label: str,
        emoji: str | None = None,
        requires_story: bool = False,
        global_owner: bool = False,
    ) -> WorkspaceUniverse:
        await self._require_taxonomy_access(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            global_owner=global_owner,
        )
        return await self._product.upsert_universe(
            workspace_id=int(workspace_id),
            key=normalize_taxonomy_key(key),
            label=normalize_taxonomy_label(label),
            emoji=normalize_emoji(emoji, fallback="🎭"),
            requires_story=bool(requires_story),
            created_by_user_id=int(actor_user_id),
        )

    async def create_story(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        universe_key: str,
        key: str,
        short_label: str,
        title: str,
        global_owner: bool = False,
    ) -> WorkspaceStory:
        await self._require_taxonomy_access(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            global_owner=global_owner,
        )
        return await self._product.upsert_story(
            workspace_id=int(workspace_id),
            universe_key=normalize_taxonomy_key(universe_key),
            key=normalize_taxonomy_key(key),
            short_label=normalize_taxonomy_label(short_label, limit=32),
            title=normalize_taxonomy_label(title, limit=192),
            created_by_user_id=int(actor_user_id),
        )

    async def import_kr_template(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        global_owner: bool = False,
    ) -> tuple[WorkspaceUniverse, int]:
        await self._require_taxonomy_access(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            global_owner=global_owner,
        )
        if int(workspace_id) == DEFAULT_WORKSPACE_ID:
            raise ValueError("КР уже является системной вселенной Velvet.")
        return await self._product.import_universe_template(
            target_workspace_id=int(workspace_id),
            source_workspace_id=DEFAULT_WORKSPACE_ID,
            universe_key="kr",
            created_by_user_id=int(actor_user_id),
        )

    async def list_categories(self, workspace_id: int) -> tuple[WorkspaceCategory, ...]:
        return await self._product.list_categories(int(workspace_id))

    async def list_universes(self, workspace_id: int) -> tuple[WorkspaceUniverse, ...]:
        return await self._product.list_universes(int(workspace_id))

    async def list_stories(
        self,
        *,
        workspace_id: int,
        universe_key: str | None = None,
    ) -> tuple[WorkspaceStory, ...]:
        return await self._product.list_stories(
            workspace_id=int(workspace_id),
            universe_key=universe_key,
        )


__all__ = (
    "WorkspaceCreationAccessError",
    "WorkspaceModuleAccessError",
    "WorkspaceProductService",
    "WorkspaceStartState",
    "normalize_emoji",
    "normalize_taxonomy_key",
    "normalize_taxonomy_label",
)
