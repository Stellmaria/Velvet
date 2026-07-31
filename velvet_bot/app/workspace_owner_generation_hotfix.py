from __future__ import annotations

import logging
import re
from typing import Any

from velvet_bot.app import auf_grs_brand_install as grs_brand
from velvet_bot.app import auf_photo_model_modes as photo_modes
from velvet_bot.app import auf_photo_ratio_callback_fix as ratio_fix
from velvet_bot.app import auf_photo_ui_install as photo_ui
from velvet_bot.app import grs_campaign_retry
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.repository import WorkspaceRepository
from velvet_bot.infrastructure.ai import KieTaskFailed
from velvet_bot.protected_bot import ProtectedMediaBot, _PROTECTED_MEDIA_METHODS
from velvet_bot.presentation.telegram import workspace_home_controller as controller

logger = logging.getLogger(__name__)

_INSTALLED = False
_ACTIVE_DATABASE: Database | None = None
_CANONICAL_PHOTO_ROUTE_INSTALLED = False
_ORIGINAL_DATABASE_INIT = Database.__init__
_ORIGINAL_PROTECTED_BOT_CALL = ProtectedMediaBot.__call__
_ORIGINAL_RETRY_DELAYS = grs_campaign_retry._retry_delays_for_error
_ORIGINAL_RETRY_REPORT = (
    grs_campaign_retry.CampaignGrsGenerationWorker._report_retry_or_terminal
)
_ORIGINAL_SANITIZE_AUF_TEXT = grs_brand._sanitize_auf_text
_ORIGINAL_INSTALL_ROUTER_PRIVACY = grs_brand._install_router_privacy
_ATTEMPT_PREFIX_RE = re.compile(r"(?mi)^(?:Попытка|Повтор):\s*")


def _capture_database_init(self: Database, *args: Any, **kwargs: Any) -> None:
    global _ACTIVE_DATABASE
    _ORIGINAL_DATABASE_INIT(self, *args, **kwargs)
    _ACTIVE_DATABASE = self


async def _user_owns_workspace(user_id: int) -> bool:
    database = _ACTIVE_DATABASE
    if database is None or int(user_id) <= 0:
        return False
    repository = WorkspaceRepository(database)
    workspaces = await repository.list_for_user(int(user_id))
    for workspace in workspaces:
        membership = await repository.get_membership(
            workspace_id=workspace.id,
            user_id=int(user_id),
        )
        if membership is not None and membership.role == "owner":
            return True
    return False


def _private_media_chat_id(method: Any) -> int | None:
    if not isinstance(method, _PROTECTED_MEDIA_METHODS):
        return None
    try:
        chat_id = int(getattr(method, "chat_id", 0) or 0)
    except (TypeError, ValueError):
        return None
    return chat_id if chat_id > 0 else None


async def _owner_aware_bot_call(
    self: ProtectedMediaBot,
    method: Any,
    request_timeout: int | None = None,
) -> Any:
    chat_id = _private_media_chat_id(method)
    permanent = getattr(
        self,
        "_permanent_unprotected_private_user_ids",
        frozenset(),
    )
    if chat_id is not None and chat_id not in permanent:
        try:
            if await _user_owns_workspace(chat_id):
                self.allow_unprotected_private_user(chat_id)
        except Exception as error:  # p2-approved-boundary: default-to-protected-media
            logger.warning(
                "Could not resolve workspace owner media access user_id=%s: %s",
                chat_id,
                error,
            )
    return await _ORIGINAL_PROTECTED_BOT_CALL(
        self,
        method,
        request_timeout=request_timeout,
    )


def _instant_provider_rejection_delays(
    error: BaseException,
    base_delay_seconds: int,
    max_delay_seconds: int,
) -> tuple[int, int]:
    if isinstance(error, KieTaskFailed):
        return 0, 0
    return _ORIGINAL_RETRY_DELAYS(
        error,
        base_delay_seconds,
        max_delay_seconds,
    )


async def _report_retry_or_terminal_without_rejection_pause(
    self: Any,
    *,
    task: Any,
    request: Any,
    progress: Any,
    failure: object,
    provider_attempt: int,
    error: Exception,
) -> None:
    will_retry = bool(getattr(failure, "will_retry", False))
    delay = int(getattr(failure, "retry_delay_seconds", 0) or 0)
    if request is not None and will_retry and delay <= 0:
        attempt = max(1, int(provider_attempt))
        await self._publish_progress(
            progress,
            task=task,
            request=request,
            percent=max(5, progress.last_percent if progress else 5),
            stage=(
                f"Попытка сервиса генерации {attempt}/{task.max_attempts} "
                "не дала результат. Следующая последовательная попытка "
                "запускается сразу."
            ),
            force=True,
        )
        return
    await _ORIGINAL_RETRY_REPORT(
        self,
        task=task,
        request=request,
        progress=progress,
        failure=failure,
        provider_attempt=provider_attempt,
        error=error,
    )


def _sanitize_auf_text_with_attempt(text: str) -> str:
    cleaned = _ORIGINAL_SANITIZE_AUF_TEXT(text)
    return _ATTEMPT_PREFIX_RE.sub("Текущая попытка: ", cleaned)


async def _canonical_photo_action(
    callback: Any,
    callback_data: Any,
    state: Any,
    access_policy: Any,
    kie_settings: Any,
    database: Any,
    ai_usage_service: Any,
    ai_task_queue_service: Any,
    auf_runtime_service: Any,
    auf_wallet_service: Any,
    auf_purchase_service: Any,
    *,
    fallback: Any,
) -> None:
    action = str(callback_data.action or "")
    if action != "create" and not action.startswith("photo"):
        await fallback(
            callback,
            callback_data,
            state,
            access_policy,
            kie_settings,
            database,
            ai_usage_service,
            ai_task_queue_service,
            auf_runtime_service,
            auf_wallet_service,
            auf_purchase_service,
        )
        return

    if not await controller.require_auf_callback(
        callback,
        workspace_id=callback_data.workspace_id,
        service=auf_runtime_service,
    ):
        return

    if action == "photo_ratio":
        data = await state.get_data()
        model = photo_modes._model(photo_modes._state_value(data, "auf_model"))
        ratio = ratio_fix.decode_photo_ratio_callback_value(callback_data.value)
        if model is None or ratio not in model.supported_aspect_ratios:
            await callback.answer("Недоступное соотношение сторон.", show_alert=True)
            return
        await state.update_data(auf_aspect_ratio=ratio)
        await photo_ui._show_auf_final(
            callback,
            state,
            database=database,
            wallet_service=auf_wallet_service,
        )
        return

    if action == "photo_format":
        if callback_data.value not in {"png", "jpeg"}:
            await callback.answer("Недоступный формат.", show_alert=True)
            return
        await state.update_data(auf_output_format=callback_data.value)
        await photo_ui._show_auf_final(
            callback,
            state,
            database=database,
            wallet_service=auf_wallet_service,
        )
        return

    if action == "photo_wan_done":
        await state.update_data(auf_wan_configured=True)
        await photo_ui._show_auf_final(
            callback,
            state,
            database=database,
            wallet_service=auf_wallet_service,
        )
        return

    if action == "photo_generate":
        await photo_ui._enqueue_auf_photo(
            callback,
            state,
            kie_settings=kie_settings,
            ai_usage_service=ai_usage_service,
            ai_task_queue_service=ai_task_queue_service,
            database=database,
        )
        return

    await photo_modes._handle_action(
        callback,
        callback_data,
        state,
        controller._AufScopedAccessPolicy(),
        kie_settings,
        database,
        ai_usage_service,
        ai_task_queue_service,
    )


def _install_canonical_photo_route() -> None:
    global _CANONICAL_PHOTO_ROUTE_INSTALLED
    if _CANONICAL_PHOTO_ROUTE_INSTALLED:
        return
    fallback = controller.handle_scoped_auf_action

    async def handle_scoped_auf_photo_action(*args: Any, **kwargs: Any) -> None:
        await _canonical_photo_action(*args, **kwargs, fallback=fallback)

    controller.install_scoped_auf_handlers(
        action_handler=handle_scoped_auf_photo_action,
    )
    _CANONICAL_PHOTO_ROUTE_INSTALLED = True


def _install_router_privacy_with_canonical_photo_route() -> None:
    _ORIGINAL_INSTALL_ROUTER_PRIVACY()
    _install_canonical_photo_route()


def install_workspace_owner_generation_hotfix() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    Database.__init__ = _capture_database_init  # type: ignore[method-assign]
    ProtectedMediaBot.__call__ = _owner_aware_bot_call  # type: ignore[method-assign]

    grs_campaign_retry._retry_delays_for_error = (
        _instant_provider_rejection_delays
    )
    grs_campaign_retry.CampaignGrsGenerationWorker._report_retry_or_terminal = (
        _report_retry_or_terminal_without_rejection_pause
    )

    grs_brand._PRIVATE_LINE_PATTERNS = tuple(
        pattern
        for pattern in grs_brand._PRIVATE_LINE_PATTERNS
        if "(?:Попытка|Повтор)" not in pattern
    )
    grs_brand._sanitize_auf_text = _sanitize_auf_text_with_attempt
    grs_brand._install_router_privacy = (
        _install_router_privacy_with_canonical_photo_route
    )
    _INSTALLED = True


__all__ = (
    "_canonical_photo_action",
    "_instant_provider_rejection_delays",
    "_sanitize_auf_text_with_attempt",
    "_user_owns_workspace",
    "install_workspace_owner_generation_hotfix",
)
