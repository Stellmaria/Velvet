#!/usr/bin/env python3
from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

import byesu_image_fallback as base

_INSTALLED = False


def _model_ids(payload: Mapping[str, object]) -> set[str]:
    raw_models = payload.get("data")
    if not isinstance(raw_models, Sequence):
        return set()
    return {
        str(item.get("id") or "").strip()
        for item in raw_models
        if isinstance(item, Mapping) and item.get("id")
    }


def _models_for_key(client: base.ByesuImageClient, api_key: str) -> set[str]:
    original_key = client.api_key
    try:
        client.api_key = api_key
        return _model_ids(client._json("/models"))
    finally:
        client.api_key = original_key


def install_byesu_dual_credentials() -> None:
    """Split Byesu analysis and media authentication without changing route semantics."""
    global _INSTALLED
    if _INSTALLED:
        return

    original_init = base.ByesuImageClient.__init__
    original_generate = base.ByesuImageClient.generate

    def init_with_dual_credentials(self: base.ByesuImageClient) -> None:
        original_init(self)
        self.analysis_api_key = self.api_key
        self.media_api_key = os.environ.get(
            "BYESU_HERMES_MEDIA_API_KEY", ""
        ).strip()
        if len(self.media_api_key) < 20:
            raise base.ByesuImageFallbackError(
                "BYESU_HERMES_MEDIA_API_KEY не настроен для image generation"
            )

    def assert_split_capabilities(
        self: base.ByesuImageClient,
        analysis_model: str,
    ) -> None:
        if analysis_model not in base._ANALYSIS_MODELS:
            raise base.ByesuImageFallbackError(
                "Недоступная GPT-5.6 модель анализа для Byesu fallback"
            )

        analysis_models = _models_for_key(self, self.analysis_api_key)
        if analysis_model not in analysis_models:
            raise base.ByesuImageFallbackError(
                "Byesu Codex token group не видит обязательную модель анализа: "
                + analysis_model
            )

        media_models = _models_for_key(self, self.media_api_key)
        if self.image_model not in media_models:
            raise base.ByesuImageFallbackError(
                "Byesu media token group не видит обязательную image-модель: "
                + self.image_model
            )

    def generate_with_media_credential(
        self: base.ByesuImageClient,
        *,
        prompt: str,
        references: Sequence[base.ByesuReference],
        size: str,
    ) -> tuple[bytes, str, str]:
        original_key = self.api_key
        try:
            self.api_key = self.media_api_key
            return original_generate(
                self,
                prompt=prompt,
                references=references,
                size=size,
            )
        finally:
            self.api_key = original_key

    base.ByesuImageClient.__init__ = init_with_dual_credentials  # type: ignore[method-assign]
    base.ByesuImageClient.assert_capabilities = assert_split_capabilities  # type: ignore[method-assign]
    base.ByesuImageClient.generate = generate_with_media_credential  # type: ignore[method-assign]
    _INSTALLED = True


__all__ = ("install_byesu_dual_credentials",)
