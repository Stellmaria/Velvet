from __future__ import annotations

import logging

from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from velvet_bot.app.commands import install_command_menus
from velvet_bot.app.dispatcher import build_dispatcher
from velvet_bot.app.workers import build_worker_manager
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.backup_runtime import BackupService
from velvet_bot.core.access import CHARACTER_EDITOR_USER_IDS
from velvet_bot.core.config import Settings, load_settings
from velvet_bot.database import Database
from velvet_bot.error_center import ErrorIncidentCenter, ErrorIncidentRepository
from velvet_bot.protected_bot import ProtectedMediaBot
from velvet_bot.reference_uploads import ReferenceUploadSessions
from velvet_bot.repositories.system_repository import SystemRepository
from velvet_bot.services.system_health import SystemHealthService
from velvet_bot.version import APP_VERSION
from velvet_bot.workers import WorkerManager

logger = logging.getLogger(__name__)


def _build_bot(settings: Settings) -> ProtectedMediaBot:
    return ProtectedMediaBot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        unprotected_private_user_ids=settings.allowed_user_ids,
    )


async def _probe_analytics_channels(
    *,
    bot: ProtectedMediaBot,
    audit_logger: TelegramAuditLogger,
    channel_ids: frozenset[int],
) -> None:
    for channel_id in sorted(channel_ids):
        try:
            chat = await bot.get_chat(channel_id)
            logger.info(
                "Channel analytics enabled: id=%s title=%s username=%s",
                channel_id,
                chat.title,
                chat.username,
            )
            await audit_logger.send(
                "Канал подключён к аналитике",
                level="SUCCESS",
                channel_id=channel_id,
                channel_title=chat.title,
                username=chat.username,
            )
        except TelegramAPIError as error:
            logger.warning(
                "Analytics channel %s is unavailable to the bot: %s",
                channel_id,
                error,
            )
            await audit_logger.send(
                "Канал аналитики недоступен",
                level="WARNING",
                channel_id=channel_id,
                error=str(error),
                hint="Добавьте бота администратором канала.",
            )


async def _close_application_resources(
    *,
    worker_manager: WorkerManager | None,
    audit_logger: TelegramAuditLogger | None,
    error_center: ErrorIncidentCenter | None,
    bot: ProtectedMediaBot | None,
    database: Database,
) -> None:
    """Release every acquired resource even when another cleanup step fails."""
    if worker_manager is not None:
        try:
            await worker_manager.stop_all()
        except Exception:
            logger.exception("Could not stop all background workers")

    if audit_logger is not None:
        try:
            await audit_logger.send("Velvet Archive остановлен", level="WARNING")
        except Exception as error:
            logger.warning("Could not send shutdown audit message: %s", error)

    # Stop the incident center only after all other components have finished so
    # cleanup failures are also delivered to the log chat.
    if error_center is not None:
        try:
            await error_center.stop()
        except Exception:
            logger.exception("Could not stop error incident center")

    if bot is not None:
        try:
            await bot.session.close()
        except Exception:
            logger.exception("Could not close Telegram bot session")

    try:
        await database.close()
    except Exception:
        logger.exception("Could not close PostgreSQL pool")


async def run_application() -> None:
    """Create all application dependencies and own their complete lifecycle."""
    settings = load_settings()
    backup_service = BackupService(
        database_url=settings.database_url,
        backup_dir=settings.backup_dir,
        pg_dump_path=settings.pg_dump_path,
        pg_restore_path=settings.pg_restore_path,
    )
    database = Database(settings.database_url)
    bot: ProtectedMediaBot | None = None
    audit_logger: TelegramAuditLogger | None = None
    error_center: ErrorIncidentCenter | None = None
    worker_manager: WorkerManager | None = None

    try:
        pre_migration_created = await backup_service.prepare_pre_migration_backup()
        if pre_migration_created:
            logger.info("Verified pre-migration PostgreSQL backup created")

        await database.initialize()
        await backup_service.persist_pre_migration_backup(database)

        system_service = SystemHealthService(
            repository=SystemRepository(database),
            backup_dir=settings.backup_dir,
            pg_dump_path=settings.pg_dump_path,
            pg_restore_path=settings.pg_restore_path,
            app_version=APP_VERSION,
        )
        bot = _build_bot(settings)
        audit_logger = TelegramAuditLogger(bot, settings.log_chat_id)
        error_center = ErrorIncidentCenter(
            bot=bot,
            repository=ErrorIncidentRepository(database),
            log_chat_id=settings.log_chat_id,
            owner_user_ids=settings.allowed_user_ids,
        )
        await error_center.start()

        reference_uploads = ReferenceUploadSessions()
        worker_manager = build_worker_manager(
            bot=bot,
            database=database,
            backup_service=backup_service,
            settings=settings,
            error_center=error_center,
        )

        bot_info = await bot.get_me()
        bot_username = bot_info.username or ""

        if bot_info.supports_guest_queries:
            logger.info("Guest Mode enabled for @%s", bot_username)
        else:
            logger.warning("Guest Mode is not enabled for @%s in BotFather", bot_username)

        bundle = build_dispatcher(
            settings=settings,
            database=database,
            bot_username=bot_username,
            audit_logger=audit_logger,
            error_center=error_center,
            reference_uploads=reference_uploads,
            backup_service=backup_service,
            system_service=system_service,
            worker_manager=worker_manager,
        )

        logger.info(
            "Owner access enabled for ids=%s usernames=%s",
            sorted(settings.allowed_user_ids),
            sorted(settings.allowed_usernames),
        )
        logger.info(
            "Character editor access enabled for ids=%s",
            sorted(CHARACTER_EDITOR_USER_IDS),
        )
        if settings.ai_vision_enabled:
            logger.info(
                "AI vision enabled provider=%s base_url=%s model=%s",
                settings.ai_vision_provider,
                settings.ai_vision_base_url,
                settings.ai_vision_model,
            )
        else:
            logger.info("AI vision disabled; media sets use fallback heuristics")

        await install_command_menus(bot, settings)
        await _probe_analytics_channels(
            bot=bot,
            audit_logger=audit_logger,
            channel_ids=settings.analytics_channel_ids,
        )

        allowed_updates = bundle.dispatcher.resolve_used_update_types()
        logger.info("Allowed Telegram updates: %s", ", ".join(allowed_updates))
        await audit_logger.send(
            "Velvet Archive запущен",
            level="SUCCESS",
            bot=f"@{bot_username}",
            app_version=APP_VERSION,
            guest_mode=bot_info.supports_guest_queries,
            allowed_updates=", ".join(allowed_updates),
            analytics_channels=", ".join(
                str(value) for value in sorted(settings.analytics_channel_ids)
            ),
            publication_timezone=settings.publication_timezone,
            managed_workers=", ".join(worker_manager.registered_names()),
            ai_vision=(
                f"{settings.ai_vision_provider}:{settings.ai_vision_model}"
                if settings.ai_vision_enabled
                else "disabled"
            ),
            backup_dir=settings.backup_dir,
            log_chat_id=settings.log_chat_id,
            error_center="enabled",
        )

        await worker_manager.start_all()
        await bundle.dispatcher.start_polling(
            bot,
            allowed_updates=allowed_updates,
            database=database,
            bot_username=bot_username,
            audit_logger=audit_logger,
            error_center=error_center,
            reference_uploads=reference_uploads,
            access_policy=bundle.access_policy,
            analytics_channel_ids=settings.analytics_channel_ids,
            publication_timezone=settings.publication_timezone,
            backup_service=backup_service,
            system_service=system_service,
            worker_manager=worker_manager,
        )
    except Exception as error:
        if error_center is not None:
            try:
                await error_center.report_exception(
                    "Критическое завершение приложения",
                    error,
                    severity="CRITICAL",
                    logger_name=__name__,
                )
            except Exception:
                logger.exception("Could not report fatal application error")
        raise
    finally:
        await _close_application_resources(
            worker_manager=worker_manager,
            audit_logger=audit_logger,
            error_center=error_center,
            bot=bot,
            database=database,
        )


__all__ = ("run_application",)
