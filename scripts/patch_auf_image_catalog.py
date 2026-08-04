from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one exact match, found {count}: {old[:80]!r}")
    write(path, content.replace(old, new, 1))


def sub_once(path: str, pattern: str, replacement: str) -> None:
    content = read(path)
    updated, count = re.subn(pattern, replacement, content, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"{path}: expected one regex match, found {count}: {pattern[:80]!r}")
    write(path, updated)


def remove_method(path: str, method_name: str) -> None:
    sub_once(
        path,
        rf"\n    def {re.escape(method_name)}\(.*?(?=\n    def |\n\nif __name__)",
        "",
    )


def patch_models() -> None:
    path = "velvet_bot/domains/media_generation/models.py"
    replace_once(
        path,
        '    WAN_27_IMAGE = "wan_27_image"\n',
        '    WAN_27_IMAGE = "wan_27_image"\n'
        '    WAN_27_IMAGE_PRO = "wan_27_image_pro"\n',
    )
    replace_once(
        path,
        '            self.WAN_27_IMAGE: "Wan 2.7 Image",\n',
        '            self.WAN_27_IMAGE: "Wan 2.7",\n'
        '            self.WAN_27_IMAGE_PRO: "Wan 2.7 Pro",\n',
    )
    sub_once(
        path,
        r"\n    KieModelAlias\.QWEN2_IMAGE_EDIT: KiePhotoModelCapabilities\(.*?\n    \),",
        "",
    )
    sub_once(
        path,
        r"\n    KieModelAlias\.FLUX_2_PRO_IMAGE: KiePhotoModelCapabilities\(.*?\n    \),",
        "",
    )
    wan_capabilities = '''    KieModelAlias.WAN_27_IMAGE: KiePhotoModelCapabilities(
        max_references=9,
        prompt_limit=5000,
        resolutions=("1K", "2K"),
        aspect_ratios=("1:1", "3:4", "4:3", "1:8", "8:1", "9:16", "16:9", "21:9"),
        default_aspect_ratio="9:16",
        supports_provider_mature_override=True,
    ),
'''
    replace_once(
        path,
        wan_capabilities,
        wan_capabilities
        + '''    KieModelAlias.WAN_27_IMAGE_PRO: KiePhotoModelCapabilities(
        max_references=9,
        prompt_limit=5000,
        resolutions=("1K", "2K", "4K"),
        aspect_ratios=("1:1", "3:4", "4:3", "1:8", "8:1", "9:16", "16:9", "21:9"),
        default_aspect_ratio="9:16",
        supports_provider_mature_override=True,
    ),
''',
    )
    replace_once(
        path,
        '    wan_27_image: str = "wan/2-7-image"\n',
        '    wan_27_image: str = "wan/2-7-image"\n'
        '    wan_27_image_pro: str = "wan/2-7-image-pro"\n',
    )
    replace_once(
        path,
        '        elif alias is KieModelAlias.WAN_27_IMAGE:\n            model = self.wan_27_image\n',
        '        elif alias is KieModelAlias.WAN_27_IMAGE:\n            model = self.wan_27_image\n'
        '        elif alias is KieModelAlias.WAN_27_IMAGE_PRO:\n            model = self.wan_27_image_pro\n',
    )
    replace_once(
        path,
        '    wan_27_1k_usd: Decimal = Decimal("0.05")\n'
        '    wan_27_2k_usd: Decimal = Decimal("0.08")\n',
        '    wan_27_1k_usd: Decimal = Decimal("0.03")\n'
        '    wan_27_2k_usd: Decimal = Decimal("0.03")\n'
        '    wan_27_pro_1k_usd: Decimal = Decimal("0.075")\n'
        '    wan_27_pro_2k_usd: Decimal = Decimal("0.075")\n'
        '    wan_27_pro_4k_usd: Decimal = Decimal("0.075")\n',
    )
    replace_once(
        path,
        '''        if request.model is KieModelAlias.WAN_27_IMAGE:
            return (
                self.wan_27_2k_usd
                if request.resolution.casefold() == "2k"
                else self.wan_27_1k_usd
            )
''',
        '''        if request.model is KieModelAlias.WAN_27_IMAGE:
            return (
                self.wan_27_2k_usd
                if request.resolution.casefold() == "2k"
                else self.wan_27_1k_usd
            )
        if request.model is KieModelAlias.WAN_27_IMAGE_PRO:
            return {
                "2k": self.wan_27_pro_2k_usd,
                "4k": self.wan_27_pro_4k_usd,
            }.get(request.resolution.casefold(), self.wan_27_pro_1k_usd)
''',
    )
    replace_once(
        path,
        '        elif self.model is KieModelAlias.WAN_27_IMAGE:\n',
        '        elif self.model in {\n'
        '            KieModelAlias.WAN_27_IMAGE,\n'
        '            KieModelAlias.WAN_27_IMAGE_PRO,\n'
        '        }:\n',
    )
    validation_anchor = '''            if self.aspect_ratio not in capabilities.aspect_ratios:
                raise ValueError(
                    f"{self.model.display_name} не поддерживает соотношение "
                    f"{self.aspect_ratio}."
                )
'''
    replace_once(
        path,
        validation_anchor,
        validation_anchor
        + '''            if (
                self.model is KieModelAlias.WAN_27_IMAGE_PRO
                and self.resolution.upper() == "4K"
                and self.input_mode is not KieInputMode.TEXT
            ):
                raise ValueError(
                    "Wan 2.7 Pro поддерживает 4K только в режиме «Только текст»."
                )
''',
    )


def patch_photo_flow() -> None:
    path = "velvet_bot/app/auf_photo_model_modes.py"
    sub_once(path, r"\n_TEXT_MODEL_IDS = \{.*?\n\}\n", "\n")
    replace_once(
        path,
        '_MAX_PROMPT_MESSAGES = 2\n',
        '_MAX_PROMPT_MESSAGES = 2\n'
        '_WAN_IMAGE_MODELS = frozenset(\n'
        '    {KieModelAlias.WAN_27_IMAGE, KieModelAlias.WAN_27_IMAGE_PRO}\n'
        ')\n',
    )
    replace_once(
        path,
        '''_PHOTO_MODELS = (
    KieModelAlias.NANO_BANANA_2,
    KieModelAlias.NANO_BANANA_PRO,
    KieModelAlias.SEEDREAM_5_PRO,
    KieModelAlias.WAN_27_IMAGE,
)
''',
        '''_PHOTO_MODELS = (
    KieModelAlias.NANO_BANANA_2,
    KieModelAlias.NANO_BANANA_PRO,
    KieModelAlias.SEEDREAM_5_PRO,
    KieModelAlias.WAN_27_IMAGE_PRO,
    KieModelAlias.WAN_27_IMAGE,
)
''',
    )
    content = read(path)
    content = content.replace(
        'model is not KieModelAlias.WAN_27_IMAGE',
        'model not in _WAN_IMAGE_MODELS',
    )
    content = content.replace(
        'model is KieModelAlias.WAN_27_IMAGE',
        'model in _WAN_IMAGE_MODELS',
    )
    content = content.replace(
        'request.model is KieModelAlias.WAN_27_IMAGE',
        'request.model in _WAN_IMAGE_MODELS',
    )
    write(path, content)

    replace_once(
        path,
        '''def _model_card(model: KieModelAlias) -> str:
    resolutions = ", ".join(model.supported_photo_resolutions)
    return (
''',
        '''def _model_card(model: KieModelAlias) -> str:
    resolutions = ", ".join(model.supported_photo_resolutions)
    wan_pro_note = (
        " 4K доступно только без референсов."
        if model is KieModelAlias.WAN_27_IMAGE_PRO
        else ""
    )
    return (
''',
    )
    replace_once(
        path,
        '        f"Качество: <b>{escape(resolutions)}</b>.\\n\\n"\n',
        '        f"Качество: <b>{escape(resolutions)}</b>.{wan_pro_note}\\n\\n"\n',
    )
    replace_once(
        path,
        '''def _resolution_keyboard(workspace_id: int, model: KieModelAlias) -> InlineKeyboardMarkup:
    rows = [
''',
        '''def _available_resolutions(
    model: KieModelAlias,
    mode: KieInputMode | None,
) -> tuple[str, ...]:
    if model is KieModelAlias.WAN_27_IMAGE_PRO and mode is not KieInputMode.TEXT:
        return tuple(
            resolution
            for resolution in model.supported_photo_resolutions
            if resolution != "4K"
        )
    return model.supported_photo_resolutions


def _resolution_keyboard(
    workspace_id: int,
    model: KieModelAlias,
    mode: KieInputMode | None = None,
) -> InlineKeyboardMarkup:
    rows = [
''',
    )
    replace_once(
        path,
        '        for resolution in model.supported_photo_resolutions\n',
        '        for resolution in _available_resolutions(model, mode)\n',
    )
    replace_once(
        path,
        '''    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    await state.set_state(ModelFirstPhotoForm.choosing_resolution)
''',
        '''    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    mode = _input_mode(_state_value(data, "auf_input_mode"))
    await state.set_state(ModelFirstPhotoForm.choosing_resolution)
''',
    )
    replace_once(
        path,
        '        reply_markup=_resolution_keyboard(workspace_id, model),\n',
        '        reply_markup=_resolution_keyboard(workspace_id, model, mode),\n',
    )
    replace_once(
        path,
        '''async def _show_wan_options(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    sequential = _wan_sequential(data)
    n = _result_count(data, KieModelAlias.WAN_27_IMAGE)
''',
        '''async def _show_wan_options(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    model = _model(_state_value(data, "auf_model"))
    if model not in _WAN_IMAGE_MODELS:
        model = KieModelAlias.WAN_27_IMAGE
    sequential = _wan_sequential(data)
    n = _result_count(data, model)
''',
    )
    replace_once(
        path,
        '            "<b>Wan 2.7 Image · количество результатов</b>\\n\\n"\n',
        '            f"<b>{escape(model.display_name)} · количество результатов</b>\\n\\n"\n',
    )
    replace_once(
        path,
        '''    resolution = str(_state_value(data, "auf_resolution") or "").strip().upper()
    if not resolution:
        resolution = model.supported_photo_resolutions[-1]
''',
        '''    resolution = str(_state_value(data, "auf_resolution") or "").strip().upper()
    if not resolution:
        available_resolutions = _available_resolutions(model, mode)
        resolution = available_resolutions[-1]
''',
    )
    replace_once(
        path,
        '''    if alias in _TEXT_MODEL_IDS and input_mode is KieInputMode.TEXT:
        variable, default = _TEXT_MODEL_IDS[alias]
        return os.getenv(variable, default).strip() or default
''',
        '',
    )
    sub_once(
        path,
        r'''    if self\.model is KieModelAlias\.QWEN2_IMAGE_EDIT:.*?(?=    if self\.model in _WAN_IMAGE_MODELS:)''',
        '',
    )
    sub_once(
        path,
        r'''    if self\.model is KieModelAlias\.FLUX_2_PRO_IMAGE:.*?(?=    return _ORIGINAL_TO_INPUT\(self\))''',
        '',
    )
    replace_once(
        path,
        '''    if str(request_value.get("model") or "") != KieModelAlias.WAN_27_IMAGE.value:
        return quote
''',
        '''    if str(request_value.get("model") or "") not in {
        model.value for model in _WAN_IMAGE_MODELS
    }:
        return quote
''',
    )
    sub_once(
        path,
        r'''async def _quote_with_wan_count\(.*?(?=\n\nasync def _submit_grs_model)''',
        '''async def _quote_with_wan_count(
    connection: Any,
    payload: Mapping[str, object],
) -> Any:
    pricing = importlib.import_module("velvet_bot.domains.auf_wallet.pricing")
    original_quote = getattr(pricing, "_original_model_first_quote")
    quote = await original_quote(connection, payload)
    request_value = payload.get("request")
    if not isinstance(request_value, Mapping):
        return quote
    if str(request_value.get("model") or "") not in {
        model.value for model in _WAN_IMAGE_MODELS
    }:
        return quote
    extra = request_value.get("extra_input")
    extra_input = dict(extra) if isinstance(extra, Mapping) else {}
    try:
        n = max(1, int(extra_input.get("n", 1)))
    except (TypeError, ValueError):
        n = 1
    if n <= 1:
        return quote

    provider_cost = quote.provider_cost_usd * Decimal(n)
    operational_multiplier = (
        Decimal("1")
        + quote.operational_cost_buffer_percent / Decimal("100")
    )
    markup_multiplier = Decimal("1") + quote.markup_percent / Decimal("100")
    target_retail_usd = provider_cost * operational_multiplier * markup_multiplier
    target_retail_rub = target_retail_usd * quote.billing_usd_to_rub
    cost_based_velvets = max(
        1,
        int(
            (target_retail_rub / quote.quote_rub_per_vl).to_integral_value(
                rounding=ROUND_CEILING
            )
        ),
    )
    quality_adjusted_velvets = (
        cost_based_velvets + quote.quality_surcharge_velvets * n
    )
    whole_velvets = max(quote.minimum_velvets * n, quality_adjusted_velvets)
    minimum_revenue_rub = quote.quote_rub_per_vl * Decimal(whole_velvets)
    return replace(
        quote,
        provider_cost_usd=provider_cost,
        target_retail_usd=target_retail_usd,
        minimum_revenue_usd=(
            minimum_revenue_rub / quote.billing_usd_to_rub
        ),
        quoted_units=whole_velvets * AUF_SCALE,
    )
''',
    )
    replace_once(
        path,
        '''        model = _model(_state_value(await state.get_data(), "auf_model"))
        resolution = str(callback_data.value).upper()
        if model is None or resolution not in model.supported_photo_resolutions:
''',
        '''        data = await state.get_data()
        model = _model(_state_value(data, "auf_model"))
        mode = _input_mode(_state_value(data, "auf_input_mode"))
        resolution = str(callback_data.value).upper()
        if model is None or resolution not in _available_resolutions(model, mode):
''',
    )


def patch_config() -> None:
    path = "velvet_bot/core/config/kie.py"
    sub_once(
        path,
        r'''        qwen2_image_edit=os\.getenv\(.*?\n        \)\.strip\(\),\n''',
        '',
    )
    sub_once(
        path,
        r'''        flux_2_pro_image=os\.getenv\(.*?\n        \)\.strip\(\),\n''',
        '',
    )
    replace_once(
        path,
        '''        wan_27_image=os.getenv(
            "KIE_WAN_27_IMAGE_MODEL",
            "wan/2-7-image",
        ).strip(),
''',
        '''        wan_27_image=os.getenv(
            "KIE_WAN_27_IMAGE_MODEL",
            "wan/2-7-image",
        ).strip(),
        wan_27_image_pro=os.getenv(
            "KIE_WAN_27_IMAGE_PRO_MODEL",
            "wan/2-7-image-pro",
        ).strip(),
''',
    )
    replace_once(
        path,
        '''            (KieModelAlias.QWEN2_IMAGE_EDIT, KieInputMode.PHOTO_TEXT),
            (KieModelAlias.WAN_27_IMAGE, KieInputMode.PHOTO_TEXT),
            (KieModelAlias.FLUX_2_PRO_IMAGE, KieInputMode.PHOTO_TEXT),
''',
        '''            (KieModelAlias.WAN_27_IMAGE, KieInputMode.PHOTO_TEXT),
            (KieModelAlias.WAN_27_IMAGE_PRO, KieInputMode.PHOTO_TEXT),
''',
    )
    replace_once(
        path,
        '''                "KIE_ENABLED=true требует model id Kie.ai для Seedream 5 Pro, "
                "Qwen Image 2.0, Wan 2.7 Image, FLUX.2 Pro и video-моделей, "
''',
        '''                "KIE_ENABLED=true требует model id Kie.ai для Seedream 5 Pro, "
                "Wan 2.7, Wan 2.7 Pro и video-моделей, "
''',
    )
    sub_once(
        path,
        r'''        qwen2_image_edit_usd=_env_decimal\(.*?\n''',
        '',
    )
    sub_once(
        path,
        r'''        flux_2_pro_1k_usd=_env_decimal\(.*?\n        flux_2_pro_2k_usd=_env_decimal\(.*?\n''',
        '',
    )
    replace_once(
        path,
        '''        wan_27_1k_usd=_env_decimal("KIE_WAN_27_IMAGE_1K_USD", "0.05"),
        wan_27_2k_usd=_env_decimal("KIE_WAN_27_IMAGE_2K_USD", "0.08"),
''',
        '''        wan_27_1k_usd=_env_decimal("KIE_WAN_27_IMAGE_1K_USD", "0.03"),
        wan_27_2k_usd=_env_decimal("KIE_WAN_27_IMAGE_2K_USD", "0.03"),
        wan_27_pro_1k_usd=_env_decimal(
            "KIE_WAN_27_IMAGE_PRO_1K_USD", "0.075"
        ),
        wan_27_pro_2k_usd=_env_decimal(
            "KIE_WAN_27_IMAGE_PRO_2K_USD", "0.075"
        ),
        wan_27_pro_4k_usd=_env_decimal(
            "KIE_WAN_27_IMAGE_PRO_4K_USD", "0.075"
        ),
''',
    )


def patch_model_catalog() -> None:
    write(
        "velvet_bot/domains/media_generation/model_catalog.py",
        '''from __future__ import annotations

MODEL_DISPLAY_NAMES: dict[str, str] = {
    "nano_banana_2": "Nano Banana 2",
    "nano_banana_pro": "Nano Banana Pro",
    "seedream_5_pro": "Seedream 5 Pro",
    "wan_27_image": "Wan 2.7",
    "wan_27_image_pro": "Wan 2.7 Pro",
    "grok_imagine_video": "Grok Imagine v1",
    "grok_imagine_video_15": "Grok Imagine Video 1.5",
    "seedance_15_pro_video": "Seedance 1.5 Pro",
    "wan_26_image_to_video": "Wan 2.7",
}


def media_model_display_name(alias: object, *, fallback: str = "Генерация") -> str:
    normalized = str(alias or "").strip()
    return MODEL_DISPLAY_NAMES.get(normalized, normalized or fallback)


__all__ = ("MODEL_DISPLAY_NAMES", "media_model_display_name")
''',
    )


def patch_migration() -> None:
    path = "migrations/z031_auf_pricing_economy_hardening.sql"
    content = read(path)
    marker = "-- Product floors preserve meaningful quality tiers after integer-VL rounding.\n"
    head, separator, _ = content.partition(marker)
    if not separator:
        raise RuntimeError(f"{path}: product floor marker not found")
    tail = '''-- Retire image routes that are no longer offered for new generations.
UPDATE auf_price_versions
SET effective_to = GREATEST(NOW(), effective_from + INTERVAL '1 microsecond'),
    source = source || '; retired from active AUF image catalog'
WHERE effective_to IS NULL
  AND operation = 'media.generate'
  AND model_alias IN ('qwen2_image_edit', 'flux_2_pro_image', 'wan_27_image');

-- Publish separate standard and Pro Wan 2.7 price versions. Provider pricing is
-- flat per result; VL floors keep product quality tiers explicit and profitable.
INSERT INTO auf_price_versions (
    version_key, provider, model_alias, resolution, audio,
    pricing_basis, unit_cost_usd, extra_reference_cost_usd,
    retail_units, extra_reference_retail_units, minimum_velvets, source
)
VALUES
    ('2026-08-04:wan-2-7-image:1k', 'kie', 'wan_27_image', '1K', NULL,
     'fixed', 0.03000000, 0, 10000, 0, 1, 'Wan 2.7 standard active catalog'),
    ('2026-08-04:wan-2-7-image:2k', 'kie', 'wan_27_image', '2K', NULL,
     'fixed', 0.03000000, 0, 20000, 0, 2, 'Wan 2.7 standard active catalog'),
    ('2026-08-04:wan-2-7-image-pro:1k', 'kie', 'wan_27_image_pro', '1K', NULL,
     'fixed', 0.07500000, 0, 30000, 0, 3, 'Wan 2.7 Pro active catalog'),
    ('2026-08-04:wan-2-7-image-pro:2k', 'kie', 'wan_27_image_pro', '2K', NULL,
     'fixed', 0.07500000, 0, 40000, 0, 4, 'Wan 2.7 Pro active catalog'),
    ('2026-08-04:wan-2-7-image-pro:4k', 'kie', 'wan_27_image_pro', '4K', NULL,
     'fixed', 0.07500000, 0, 50000, 0, 5, 'Wan 2.7 Pro text-to-image only')
ON CONFLICT (version_key) DO UPDATE
SET effective_to = NULL,
    unit_cost_usd = EXCLUDED.unit_cost_usd,
    retail_units = EXCLUDED.retail_units,
    extra_reference_cost_usd = EXCLUDED.extra_reference_cost_usd,
    extra_reference_retail_units = EXCLUDED.extra_reference_retail_units,
    minimum_velvets = EXCLUDED.minimum_velvets,
    source = EXCLUDED.source;

-- Product floors preserve meaningful quality tiers after integer-VL rounding.
UPDATE auf_price_versions
SET minimum_velvets = CASE
    WHEN model_alias = 'nano_banana_2' AND UPPER(COALESCE(resolution, '')) = '1K' THEN 1
    WHEN model_alias = 'nano_banana_2' AND UPPER(COALESCE(resolution, '')) = '2K' THEN 2
    WHEN model_alias = 'nano_banana_2' AND UPPER(COALESCE(resolution, '')) = '4K' THEN 3
    WHEN model_alias = 'nano_banana_pro' AND UPPER(COALESCE(resolution, '')) = '1K' THEN 2
    WHEN model_alias = 'nano_banana_pro' AND UPPER(COALESCE(resolution, '')) = '2K' THEN 3
    WHEN model_alias = 'nano_banana_pro' AND UPPER(COALESCE(resolution, '')) = '4K' THEN 4
    WHEN model_alias = 'seedream_5_pro' AND UPPER(COALESCE(resolution, '')) = '1K' THEN 2
    WHEN model_alias = 'seedream_5_pro' AND UPPER(COALESCE(resolution, '')) = '2K' THEN 4
    WHEN model_alias = 'wan_27_image' AND UPPER(COALESCE(resolution, '')) = '1K' THEN 1
    WHEN model_alias = 'wan_27_image' AND UPPER(COALESCE(resolution, '')) = '2K' THEN 2
    WHEN model_alias = 'wan_27_image_pro' AND UPPER(COALESCE(resolution, '')) = '1K' THEN 3
    WHEN model_alias = 'wan_27_image_pro' AND UPPER(COALESCE(resolution, '')) = '2K' THEN 4
    WHEN model_alias = 'wan_27_image_pro' AND UPPER(COALESCE(resolution, '')) = '4K' THEN 5
    ELSE 1
END,
source = source || '; stable quote reference and SKU floor'
WHERE effective_from <= NOW()
  AND (effective_to IS NULL OR effective_to > NOW())
  AND operation = 'media.generate';
'''
    write(path, head + tail)


def patch_photo_tests() -> None:
    path = "tests/test_auf_photo_model_modes.py"
    content = read(path)
    content = content.replace(
        '''            KieModelAlias.QWEN2_IMAGE_EDIT: (3, 8000),
            KieModelAlias.WAN_27_IMAGE: (9, 5000),
            KieModelAlias.FLUX_2_PRO_IMAGE: (8, 5000),
''',
        '''            KieModelAlias.WAN_27_IMAGE: (9, 5000),
            KieModelAlias.WAN_27_IMAGE_PRO: (9, 5000),
''',
    )
    write(path, content)
    remove_method(path, "test_flux_photo_payload_keeps_uploaded_reference")
    remove_method(path, "test_text_routes_do_not_require_fake_reference")
    replace_once(
        path,
        '''    def test_seedream_output_format_is_selected_only_for_seedream(self) -> None:
''',
        '''    def test_active_catalog_contains_only_five_approved_models(self) -> None:
        self.assertEqual(
            (
                KieModelAlias.NANO_BANANA_2,
                KieModelAlias.NANO_BANANA_PRO,
                KieModelAlias.SEEDREAM_5_PRO,
                KieModelAlias.WAN_27_IMAGE_PRO,
                KieModelAlias.WAN_27_IMAGE,
            ),
            modes._PHOTO_MODELS,
        )

    def test_wan_provider_routes_are_distinct(self) -> None:
        catalog = KieModelCatalog()
        self.assertEqual(
            "wan/2-7-image",
            modes._provider_model(
                catalog,
                KieModelAlias.WAN_27_IMAGE,
                input_mode=KieInputMode.TEXT,
            ),
        )
        self.assertEqual(
            "wan/2-7-image-pro",
            modes._provider_model(
                catalog,
                KieModelAlias.WAN_27_IMAGE_PRO,
                input_mode=KieInputMode.TEXT,
            ),
        )

    def test_wan_text_routes_do_not_require_fake_reference(self) -> None:
        for model, resolution in (
            (KieModelAlias.WAN_27_IMAGE, "2K"),
            (KieModelAlias.WAN_27_IMAGE_PRO, "4K"),
        ):
            with self.subTest(model=model):
                request = KieGenerationRequest(
                    model=model,
                    input_mode=KieInputMode.TEXT,
                    prompt="text only",
                    resolution=resolution,
                    aspect_ratio="9:16",
                )
                payload = modes._to_input(request)
                self.assertNotIn("input_urls", payload)

    def test_seedream_output_format_is_selected_only_for_seedream(self) -> None:
''',
    )
    replace_once(path, '        self.assertEqual(Decimal("0.48"), cost)\n', '        self.assertEqual(Decimal("0.18"), cost)\n')


def patch_capability_tests() -> None:
    write(
        "tests/test_photo_model_capabilities.py",
        '''from __future__ import annotations

import unittest
from decimal import Decimal

from velvet_bot.domains.media_generation import (
    KieContentMode,
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KiePricing,
    KieReferenceImage,
)


def _references(count: int) -> tuple[KieReferenceImage, ...]:
    return tuple(
        KieReferenceImage(
            telegram_file_id=f"file-{index}",
            telegram_file_unique_id=f"unique-{index}",
            source="upload",
            file_name=f"{index}.jpg",
        )
        for index in range(count)
    )


class PhotoCapabilityMapTests(unittest.TestCase):
    def test_active_image_capabilities_cover_only_approved_models(self) -> None:
        expected = {
            KieModelAlias.SEEDREAM_5_PRO: (10, 8000, ("1K", "2K")),
            KieModelAlias.NANO_BANANA_2: (5, 8000, ("1K", "2K", "4K")),
            KieModelAlias.NANO_BANANA_PRO: (5, 8000, ("1K", "2K", "4K")),
            KieModelAlias.WAN_27_IMAGE: (9, 5000, ("1K", "2K")),
            KieModelAlias.WAN_27_IMAGE_PRO: (9, 5000, ("1K", "2K", "4K")),
        }
        for model, (references, prompt, resolutions) in expected.items():
            with self.subTest(model=model):
                self.assertTrue(model.is_photo_model)
                self.assertEqual(references, model.max_photo_references)
                self.assertEqual(prompt, model.photo_prompt_limit)
                self.assertEqual(resolutions, model.supported_photo_resolutions)
        self.assertFalse(KieModelAlias.QWEN2_IMAGE_EDIT.is_photo_model)
        self.assertFalse(KieModelAlias.FLUX_2_PRO_IMAGE.is_photo_model)

    def test_request_rejects_wan_reference_overflow(self) -> None:
        with self.assertRaisesRegex(ValueError, "принимает не больше 9"):
            KieGenerationRequest(
                model=KieModelAlias.WAN_27_IMAGE,
                input_mode=KieInputMode.PHOTO_TEXT,
                prompt="edit",
                references=_references(10),
                aspect_ratio="9:16",
                resolution="2K",
            )

    def test_wan_pro_4k_is_text_only(self) -> None:
        with self.assertRaisesRegex(ValueError, "4K только"):
            KieGenerationRequest(
                model=KieModelAlias.WAN_27_IMAGE_PRO,
                input_mode=KieInputMode.PHOTO_TEXT,
                prompt="edit",
                references=_references(1),
                aspect_ratio="9:16",
                resolution="4K",
            )
        request = KieGenerationRequest(
            model=KieModelAlias.WAN_27_IMAGE_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="premium poster",
            aspect_ratio="9:16",
            resolution="4K",
        )
        self.assertEqual("4K", request.resolution)

    def test_archive_source_and_workspace_survive_queue_snapshot(self) -> None:
        reference = KieReferenceImage(
            telegram_file_id="system-file",
            source="system",
            character_id=7,
            reference_id=9,
            workspace_id=1,
        )
        restored = KieReferenceImage.from_payload(reference.to_payload())
        self.assertEqual("system", restored.source)
        self.assertEqual(1, restored.workspace_id)
        self.assertEqual(9, restored.reference_id)


class PhotoProviderPayloadTests(unittest.TestCase):
    def test_wan_variants_share_provider_payload_contract(self) -> None:
        for model, resolution in (
            (KieModelAlias.WAN_27_IMAGE, "2K"),
            (KieModelAlias.WAN_27_IMAGE_PRO, "2K"),
        ):
            with self.subTest(model=model):
                request = KieGenerationRequest(
                    model=model,
                    input_mode=KieInputMode.PHOTO_TEXT,
                    prompt="edit only the requested details",
                    references=_references(2),
                    image_urls=(
                        "https://cdn.example/one.jpg",
                        "https://cdn.example/two.jpg",
                    ),
                    content_mode=KieContentMode.MATURE,
                    aspect_ratio="9:16",
                    resolution=resolution,
                )
                payload = request.to_input()
                self.assertEqual(1, payload["n"])
                self.assertIs(False, payload["enable_sequential"])
                self.assertIs(False, payload["thinking_mode"])
                self.assertIs(False, payload["watermark"])
                self.assertIs(False, payload["nsfw_checker"])
                self.assertEqual([[], []], payload["bbox_list"])

    def test_preflight_pricing_is_configurable_per_wan_variant(self) -> None:
        pricing = KiePricing(
            wan_27_1k_usd=Decimal("0.031"),
            wan_27_2k_usd=Decimal("0.032"),
            wan_27_pro_1k_usd=Decimal("0.076"),
            wan_27_pro_2k_usd=Decimal("0.077"),
            wan_27_pro_4k_usd=Decimal("0.078"),
        )
        expected = {
            (KieModelAlias.WAN_27_IMAGE, "1K"): Decimal("0.031"),
            (KieModelAlias.WAN_27_IMAGE, "2K"): Decimal("0.032"),
            (KieModelAlias.WAN_27_IMAGE_PRO, "1K"): Decimal("0.076"),
            (KieModelAlias.WAN_27_IMAGE_PRO, "2K"): Decimal("0.077"),
            (KieModelAlias.WAN_27_IMAGE_PRO, "4K"): Decimal("0.078"),
        }
        for (model, resolution), cost in expected.items():
            request = KieGenerationRequest(
                model=model,
                input_mode=KieInputMode.TEXT,
                prompt="image",
                aspect_ratio="1:1",
                resolution=resolution,
            )
            self.assertEqual(cost, pricing.estimate_usd(request))


if __name__ == "__main__":
    unittest.main()
''',
    )


def patch_pricing_tests() -> None:
    path = "tests/test_auf_owner_cost_only_pricing.py"
    replace_once(
        path,
        '''            minimums = {
                "nano_banana_2": {"1K": 1, "2K": 2, "4K": 3},
                "nano_banana_pro": {"1K": 2, "2K": 3, "4K": 4},
            }
''',
        '''            minimums = {
                "nano_banana_2": {"1K": 1, "2K": 2, "4K": 3},
                "nano_banana_pro": {"1K": 2, "2K": 3, "4K": 4},
                "wan_27_image": {"1K": 1, "2K": 2},
                "wan_27_image_pro": {"1K": 3, "2K": 4, "4K": 5},
            }
''',
    )
    replace_once(
        path,
        '''

class OwnerCostOnlyTests(unittest.TestCase):
''',
        '''

class WanImagePriceTests(unittest.IsolatedAsyncioTestCase):
    async def test_standard_and_pro_keep_separate_price_grids(self) -> None:
        expected_by_model = {
            "wan_27_image": {"1K": 1, "2K": 2},
            "wan_27_image_pro": {"1K": 3, "2K": 4, "4K": 5},
        }
        costs = {
            "wan_27_image": Decimal("0.03"),
            "wan_27_image_pro": Decimal("0.075"),
        }
        for model, expected in expected_by_model.items():
            for resolution, velvets in expected.items():
                with self.subTest(model=model, resolution=resolution):
                    quote = await quote_auf_payload(
                        _Connection(
                            model_alias=model,
                            resolution=resolution,
                            unit_cost_usd=costs[model],
                        ),
                        _payload(model, resolution),
                    )
                    self.assertEqual(velvets * AUF_SCALE, quote.quoted_units)

    async def test_individual_markup_does_not_collapse_wan_pro_floor(self) -> None:
        quote = await quote_auf_payload(
            _Connection(
                model_alias="wan_27_image_pro",
                resolution="1K",
                unit_cost_usd=Decimal("0.075"),
                override=Decimal("15"),
            ),
            _payload("wan_27_image_pro", "1K"),
        )
        self.assertEqual(3 * AUF_SCALE, quote.quoted_units)


class OwnerCostOnlyTests(unittest.TestCase):
''',
    )


def patch_worklog() -> None:
    path = "docs/worklog/2026-08-04-auf-pricing-economy-hardening.md"
    replace_once(
        path,
        '''- Banana Pro получает сетку 2/3/4 VL.
- Качество Wan Image и FLUX сохраняет отдельные ценовые уровни.
''',
        '''- Banana Pro получает сетку 2/3/4 VL.
- Активный каталог изображений ограничен пятью моделями: Banana 2, Banana Pro, Seedream 5 Pro, Wan 2.7 и Wan 2.7 Pro.
- Wan 2.7 использует отдельный provider ID `wan/2-7-image` и сетку 1/2 VL.
- Wan 2.7 Pro использует `wan/2-7-image-pro` и сетку 3/4/5 VL; 4K доступно только без референсов.
- Qwen Image и FLUX удалены из активных capability/config/pricing-контуров; durable aliases сохранены только для чтения исторических задач.
- Повторный Wan-пересчёт больше не читает `auf_package_prices` и не умножает стоимость дважды.
''',
    )


def main() -> None:
    patch_models()
    patch_photo_flow()
    patch_config()
    patch_model_catalog()
    patch_migration()
    patch_photo_tests()
    patch_capability_tests()
    patch_pricing_tests()
    patch_worklog()


if __name__ == "__main__":
    main()
