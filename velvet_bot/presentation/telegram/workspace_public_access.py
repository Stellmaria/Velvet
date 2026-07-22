from __future__ import annotations

from aiogram import Bot
from aiogram.types import User

from velvet_bot.access import AccessPolicy
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError
from velvet_bot.public_adult_access import has_adult_channel_access
from velvet_bot.public_manager_access import has_public_manager_access


async def has_archive_manager_access(
    *,
    user: User | None,
    access_policy: AccessPolicy,
    workspace_id: int,
    workspace_product_service: WorkspaceProductService | None,
) -> bool:
    if has_public_manager_access(user, access_policy):
        return True
    if (
        user is None
        or int(workspace_id) == DEFAULT_WORKSPACE_ID
        or workspace_product_service is None
    ):
        return False
    try:
        membership = await workspace_product_service.require_role(
            workspace_id=int(workspace_id),
            actor_user_id=int(user.id),
            minimum_role="owner",
        )
    except WorkspaceAccessError:
        return False
    return membership.role == "owner"


async def workspace_channel_id(
    *,
    workspace_id: int,
    kind: str,
    workspace_product_service: WorkspaceProductService | None,
) -> int | None:
    if workspace_product_service is None:
        return None
    channels = await workspace_product_service.list_channels(int(workspace_id))
    channel = next((item for item in channels if item.kind == kind), None)
    return int(channel.chat_id) if channel is not None else None


async def has_workspace_adult_access(
    *,
    bot: Bot,
    user_id: int,
    workspace_id: int,
    manager_access: bool,
    default_adult_channel_id: int,
    workspace_product_service: WorkspaceProductService | None,
) -> bool:
    if manager_access:
        return True
    channel_id = (
        int(default_adult_channel_id)
        if int(workspace_id) == DEFAULT_WORKSPACE_ID
        else await workspace_channel_id(
            workspace_id=workspace_id,
            kind="adult",
            workspace_product_service=workspace_product_service,
        )
    )
    if channel_id is None:
        return False
    return await has_adult_channel_access(bot, user_id, channel_id=channel_id)


async def has_workspace_download_access(
    *,
    bot: Bot,
    user_id: int,
    workspace_id: int,
    member_access: bool,
    manager_access: bool,
    workspace_product_service: WorkspaceProductService | None,
) -> bool:
    if manager_access or int(workspace_id) == DEFAULT_WORKSPACE_ID:
        return member_access or manager_access
    if workspace_product_service is None:
        return False
    settings = await workspace_product_service.get_settings(workspace_id)
    if settings.download_audience == "disabled":
        return False
    if settings.download_audience == "all":
        return True
    channel_id = await workspace_channel_id(
        workspace_id=workspace_id,
        kind="download",
        workspace_product_service=workspace_product_service,
    )
    if channel_id is None:
        return False
    return await has_adult_channel_access(bot, user_id, channel_id=channel_id)


__all__ = (
    "has_archive_manager_access",
    "has_workspace_adult_access",
    "has_workspace_download_access",
    "workspace_channel_id",
)
