from __future__ import annotations

from dataclasses import dataclass

from aiogram import Dispatcher

from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.backup_runtime import BackupService
from velvet_bot.core.access import AccessPolicy
from velvet_bot.core.config import Settings
from velvet_bot.database import Database
from velvet_bot.discussion_analytics_middleware import DiscussionAnalyticsMiddleware
from velvet_bot.presentation.telegram.middleware import OwnerAccessMiddleware
from velvet_bot.presentation.telegram.router import get_root_router
from velvet_bot.publication_inbox_middleware import PublicationInboxMiddleware
from velvet_bot.reference_uploads import ReferenceUploadSessions
from velvet_bot.services.system_health import SystemHealthService
from velvet_bot.workers import WorkerManager


@dataclass(frozen=True, slots=True)
class DispatcherBundle:
    dispatcher: Dispatcher
    access_policy: AccessPolicy


def build_dispatcher(
    *,
    settings: Settings,
    database: Database,
    bot_username: str,
    audit_logger: TelegramAuditLogger,
    reference_uploads: ReferenceUploadSessions,
    backup_service: BackupService,
    system_service: SystemHealthService,
    worker_manager: WorkerManager,
) -> DispatcherBundle:
    """Build the Telegram dispatcher and its dependency-injection context."""
    access_policy = AccessPolicy(
        allowed_user_ids=settings.allowed_user_ids,
        allowed_usernames=settings.allowed_usernames,
    )
    access_middleware = OwnerAccessMiddleware(access_policy)
    publication_inbox_middleware = PublicationInboxMiddleware()
    discussion_middleware = DiscussionAnalyticsMiddleware()

    dispatcher = Dispatcher()
    dispatcher.workflow_data.update(
        {
            "database": database,
            "bot_username": bot_username,
            "audit_logger": audit_logger,
            "reference_uploads": reference_uploads,
            "access_policy": access_policy,
            "analytics_channel_ids": settings.analytics_channel_ids,
            "publication_timezone": settings.publication_timezone,
            "backup_service": backup_service,
            "system_service": system_service,
            "worker_manager": worker_manager,
        }
    )

    dispatcher.message.outer_middleware(access_middleware)
    dispatcher.message.outer_middleware(publication_inbox_middleware)
    dispatcher.message.outer_middleware(discussion_middleware)
    dispatcher.edited_message.outer_middleware(access_middleware)
    dispatcher.edited_message.outer_middleware(discussion_middleware)
    dispatcher.guest_message.outer_middleware(access_middleware)
    dispatcher.callback_query.outer_middleware(access_middleware)
    dispatcher.inline_query.outer_middleware(access_middleware)
    dispatcher.include_router(get_root_router())

    return DispatcherBundle(
        dispatcher=dispatcher,
        access_policy=access_policy,
    )


__all__ = ("DispatcherBundle", "build_dispatcher")
