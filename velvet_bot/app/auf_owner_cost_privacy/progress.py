from __future__ import annotations

from typing import Any

from velvet_bot.app.auf_owner_cost_privacy.formatting import (
    progress_text_for_user,
    strip_attempt_details,
)


def install_owner_aware_progress_policy(brand_module: Any) -> None:
    """Preserve internal progress only for the global creator."""

    def wrap_progress_method(cls: type[Any]) -> None:
        original = getattr(cls, "_friendly_progress_text", None)
        if not callable(original) or getattr(original, "__auf_privacy_wrapped__", False):
            return

        def wrapped(
            self: Any,
            *,
            task: Any,
            request: Any,
            percent: int,
            stage: str,
        ) -> str:
            rendered = original(
                self,
                task=task,
                request=request,
                percent=percent,
                stage=stage,
            )
            payload = getattr(task, "payload", {})
            user_id = payload.get("user_id") if hasattr(payload, "get") else None
            return progress_text_for_user(
                rendered,
                user_id=user_id,
                sanitizer=brand_module._sanitize_auf_text,
            )

        wrapped.__auf_privacy_wrapped__ = True  # type: ignore[attr-defined]
        cls._friendly_progress_text = wrapped  # type: ignore[method-assign]

    brand_module._wrap_progress_method = wrap_progress_method


def install_public_receipt_policy(receipt_module: Any) -> None:
    original = receipt_module.build_public_result_caption

    def build_public_result_caption(request: Any, receipt: Any) -> str:
        return strip_attempt_details(original(request, receipt))

    receipt_module.build_public_result_caption = build_public_result_caption


__all__ = (
    "install_owner_aware_progress_policy",
    "install_public_receipt_policy",
)
