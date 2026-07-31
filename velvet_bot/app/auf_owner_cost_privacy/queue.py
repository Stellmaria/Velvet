from __future__ import annotations

from contextvars import ContextVar
from decimal import Decimal
from typing import Any

from velvet_bot.app.auf_owner_cost_privacy.formatting import (
    is_global_owner,
    owner_cost_block,
    owner_cost_block_from_values,
    rewrite_owner_queue_confirmation,
)
from velvet_bot.domains.auf_wallet import AufPricingRepository

_OWNER_QUEUE_COST: ContextVar[str | None] = ContextVar(
    "auf_owner_queue_cost",
    default=None,
)


def install_owner_queue_confirmations(photo_ui: Any, portal: Any) -> None:
    original_photo_edit = photo_ui.edit_or_answer_auf_callback
    original_video_edit = portal.video_core.edit_or_answer
    original_photo_enqueue = photo_ui._enqueue_auf_photo
    original_video_submit = portal._submit_video_with_auf

    async def photo_edit(callback: Any, *args: Any, **kwargs: Any) -> Any:
        cost_block = _OWNER_QUEUE_COST.get()
        text = kwargs.get("text")
        if (
            cost_block
            and is_global_owner(callback.from_user.id)
            and isinstance(text, str)
        ):
            kwargs["text"] = rewrite_owner_queue_confirmation(text, cost_block)
        return await original_photo_edit(callback, *args, **kwargs)

    async def video_edit(callback: Any, *args: Any, **kwargs: Any) -> Any:
        cost_block = _OWNER_QUEUE_COST.get()
        text = kwargs.get("text")
        if (
            cost_block
            and is_global_owner(callback.from_user.id)
            and isinstance(text, str)
        ):
            kwargs["text"] = rewrite_owner_queue_confirmation(text, cost_block)
        return await original_video_edit(callback, *args, **kwargs)

    async def enqueue_photo(
        callback: Any,
        state: Any,
        **kwargs: Any,
    ) -> Any:
        if not is_global_owner(callback.from_user.id):
            return await original_photo_enqueue(callback, state, **kwargs)
        data = await state.get_data()
        request = photo_ui.photo_router._request(data)
        workspace_id = int(photo_ui._state_value(data, "auf_workspace_id") or 0)
        quote = await AufPricingRepository(kwargs["database"]).quote(
            {
                "workspace_id": workspace_id,
                "user_id": callback.from_user.id,
                "request": request.to_task_payload(),
            }
        )
        token = _OWNER_QUEUE_COST.set(owner_cost_block(quote))
        try:
            return await original_photo_enqueue(callback, state, **kwargs)
        finally:
            _OWNER_QUEUE_COST.reset(token)

    async def submit_video(
        callback: Any,
        *,
        state: Any,
        workspace_id: int,
        kie_settings: Any,
        ai_usage_service: Any,
        ai_task_queue_service: Any,
        wallet_service: Any,
    ) -> Any:
        if not is_global_owner(callback.from_user.id):
            return await original_video_submit(
                callback,
                state=state,
                workspace_id=workspace_id,
                kie_settings=kie_settings,
                ai_usage_service=ai_usage_service,
                ai_task_queue_service=ai_task_queue_service,
                wallet_service=wallet_service,
            )
        request, *_rest = portal._video_request_from_state(await state.get_data())
        usd = Decimal(kie_settings.pricing.estimate_usd(request))
        rub = Decimal(
            kie_settings.pricing.estimate_rub(
                request,
                usd_to_rub=kie_settings.usd_to_rub,
            )
        )
        settings = await wallet_service.economy_settings(
            actor_user_id=callback.from_user.id
        )
        byn = usd * Decimal(settings.billing_usd_to_byn)
        token = _OWNER_QUEUE_COST.set(
            owner_cost_block_from_values(
                provider="kie",
                usd=usd,
                rub=rub,
                byn=byn,
            )
        )
        try:
            return await original_video_submit(
                callback,
                state=state,
                workspace_id=workspace_id,
                kie_settings=kie_settings,
                ai_usage_service=ai_usage_service,
                ai_task_queue_service=ai_task_queue_service,
                wallet_service=wallet_service,
            )
        finally:
            _OWNER_QUEUE_COST.reset(token)

    photo_ui.edit_or_answer_auf_callback = photo_edit
    portal.video_core.edit_or_answer = video_edit
    photo_ui._enqueue_auf_photo = enqueue_photo
    portal._submit_video_with_auf = submit_video


__all__ = ("install_owner_queue_confirmations",)
