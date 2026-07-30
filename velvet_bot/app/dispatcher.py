from __future__ import annotations

from dataclasses import dataclass

from aiogram import Dispatcher

from velvet_bot.app.ai_usage import build_audited_ai_usage_service
from velvet_bot.app.save_sessions import SaveUploadSessions
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.backup_runtime import BackupService
from velvet_bot.core.access import AccessPolicy
from velvet_bot.core.config import Settings
from velvet_bot.core.config.kie import KieSettings, load_kie_settings
from velvet_bot.database import Database
from velvet_bot.discussion_analytics_middleware import DiscussionAnalyticsMiddleware
from velvet_bot.domains.ai_usage import AITaskQueueService, AIUsageService
from velvet_bot.domains.meow_runtime import MeowRuntimeRepository, MeowRuntimeService
from velvet_bot.domains.meow_wallet import (
    MeowPurchaseRepository,
    MeowPurchaseService,
    MeowWalletRepository,
    MeowWalletService,
    build_meow_charged_task_queue_service,
)
from velvet_bot.domains.roleplay import build_roleplay_service
from velvet_bot.domains.workspaces.character_management import WorkspaceCharacterService
from velvet_bot.domains.workspaces.product_repository import WorkspaceProductRepository
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.repository import WorkspaceRepository
from velvet_bot.domains.workspaces.service import WorkspaceService
from velvet_bot.error_center import ErrorIncidentCenter
from velvet_bot.presentation.telegram.middleware import OwnerAccessMiddleware
from velvet_bot.presentation.telegram.router import get_root_router
from velvet_bot.publication_inbox_middleware import PublicationInboxMiddleware
from velvet_bot.reference_uploads import ReferenceUploadSessions
from velvet_bot.services.diagnostic_bundle import DiagnosticBundleService
from velvet_bot.services.system_health import SystemHealthService
from velvet_bot.supervisor_client import build_supervisor_client
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
    diagnostic_service: DiagnosticBundleService,
    worker_manager: WorkerManager,
    ai_usage_service: AIUsageService | None = None,
    ai_task_queue_service: AITaskQueueService | None = None,
    kie_settings: KieSettings | None = None,
    error_center: ErrorIncidentCenter | None = None,
    save_upload_sessions: SaveUploadSessions | None = None,
) -> DispatcherBundle:
    access_policy = AccessPolicy(
        allowed_user_ids=settings.allowed_user_ids,
        allowed_usernames=settings.allowed_usernames,
        moderator_user_ids=settings.moderator_user_ids,
    )
    access_middleware = OwnerAccessMiddleware(access_policy)
    publication_inbox_middleware = PublicationInboxMiddleware()
    discussion_middleware = DiscussionAnalyticsMiddleware()
    supervisor_client = build_supervisor_client()
    active_save_upload_sessions = save_upload_sessions or SaveUploadSessions()
    workspace_repository = WorkspaceRepository(database)
    workspace_service = WorkspaceService(workspace_repository)
    workspace_product_service = WorkspaceProductService(
        product_repository=WorkspaceProductRepository(database),
        workspace_repository=workspace_repository,
    )
    workspace_character_service = WorkspaceCharacterService(database)
    meow_runtime_service = MeowRuntimeService(MeowRuntimeRepository(database))
    meow_wallet_service = MeowWalletService(
        MeowWalletRepository(database),
        meow_runtime_service,
    )
    meow_purchase_service = MeowPurchaseService(
        MeowPurchaseRepository(database),
        meow_runtime_service,
    )

    active_ai_usage_service = ai_usage_service or build_audited_ai_usage_service(
        database=database,
        audit_logger=audit_logger,
    )
    active_task_queue_service = (
        ai_task_queue_service
        or build_meow_charged_task_queue_service(database=database)
    )
    active_kie_settings = kie_settings or load_kie_settings()
    roleplay_service = build_roleplay_service(
        settings=settings,
        database=database,
        ai_usage_service=active_ai_usage_service,
    )

    workflow_data = {
        "database": database,
        "bot_username": bot_username,
        "audit_logger": audit_logger,
        "reference_uploads": reference_uploads,
        "save_upload_sessions": active_save_upload_sessions,
        "access_policy": access_policy,
        "workspace_service": workspace_service,
        "workspace_product_service": workspace_product_service,
        "workspace_characters": workspace_character_service,
        "meow_runtime_service": meow_runtime_service,
        "meow_wallet_service": meow_wallet_service,
        "meow_purchase_service": meow_purchase_service,
        "roleplay_service": roleplay_service,
        "ai_usage_service": active_ai_usage_service,
        "ai_task_queue_service": active_task_queue_service,
        "kie_settings": active_kie_settings,
        "analytics_channel_ids": settings.analytics_channel_ids,
        "adult_channel_id": settings.adult_channel_id,
        "publication_timezone": settings.publication_timezone,
        "backup_service": backup_service,
        "system_service": system_service,
        "diagnostic_service": diagnostic_service,
        "worker_manager": worker_manager,
        "supervisor_client": supervisor_client,
    }
    if error_center is not None:
        workflow_data["error_center"] = error_center

    dispatcher = Dispatcher()
    dispatcher.workflow_data.update(workflow_data)
    dispatcher.message.outer_middleware(access_middleware)
    dispatcher.message.outer_middleware(publication_inbox_middleware)
    dispatcher.message.outer_middleware(discussion_middleware)
    dispatcher.edited_message.outer_middleware(access_middleware)
    dispatcher.edited_message.outer_middleware(discussion_middleware)
    dispatcher.guest_message.outer_middleware(access_middleware)
    dispatcher.callback_query.outer_middleware(access_middleware)
    dispatcher.inline_query.outer_middleware(access_middleware)
    dispatcher.include_router(get_root_router())
    return DispatcherBundle(dispatcher=dispatcher, access_policy=access_policy)


__all__ = ("DispatcherBundle", "build_dispatcher")
