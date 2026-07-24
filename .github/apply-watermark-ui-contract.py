from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one block in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


ui = Path("velvet_bot/watermark_ui.py")
replace_once(
    ui,
    """def build_watermark_keyboard(item: WatermarkWorkItem) -> InlineKeyboardMarkup:
    if item.job.archive_media_id is not None:
        return build_archive_watermark_review_keyboard(item)
    rows = _settings_rows(item)
    rows.append([_button("✅ Скачать PNG без сжатия", "approve", item.job.id)])
    rows.append([_button("✖ Отмена", "cancel", item.job.id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
""",
    """def build_watermark_keyboard(item: WatermarkWorkItem) -> InlineKeyboardMarkup:
    status = item.revision.status
    if status in {"draft", "error"}:
        rows = _settings_rows(item)
        rows.append(
            [_button("▶️ Сгенерировать preview", "generate", item.job.id)]
        )
        rows.append([_button("✖ Отмена", "cancel", item.job.id)])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    if status in {"pending", "processing"}:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    _button(
                        "⏳ Генерация выполняется",
                        "draft_noop",
                        item.job.id,
                    )
                ],
                [_button("✖ Отмена", "cancel", item.job.id)],
            ]
        )
    if item.job.archive_media_id is not None:
        return build_archive_watermark_review_keyboard(item)
    rows = _settings_rows(item)
    rows.append([_button("✅ Скачать PNG без сжатия", "approve", item.job.id)])
    rows.append([_button("✖ Отмена", "cancel", item.job.id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
""",
)
replace_once(
    ui,
    """def format_watermark_caption(item: WatermarkWorkItem, *, status_text: str | None = None) -> str:
    settings = item.revision.settings
""",
    """def format_watermark_caption(item: WatermarkWorkItem, *, status_text: str | None = None) -> str:
    if item.revision.status == "draft":
        status_text = (
            "черновик: выберите все параметры и затем нажмите "
            "«Сгенерировать preview»"
        )
    elif item.revision.status == "error" and status_text is None:
        status_text = "ошибка: измените параметры или повторите генерацию"
    settings = item.revision.settings
""",
)

controller = Path(
    "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
    "workspace_product_experience.py"
)
text = controller.read_text(encoding="utf-8")
for old in (
    "from velvet_bot.domains.watermark.models import WatermarkWorkItem\n",
    "from velvet_bot.presentation.telegram.routers.public_archive import watermark_actions\n",
):
    if old not in text:
        raise RuntimeError(f"Missing controller import: {old!r}")
    text = text.replace(old, "", 1)
for old in (
    "_ORIGINAL_SETTINGS_ROWS = watermark_ui._settings_rows\n",
    "_ORIGINAL_WATERMARK_BUTTON = watermark_ui._button\n",
    "_ORIGINAL_WATERMARK_KEYBOARD = watermark_ui.build_watermark_keyboard\n",
    "_ORIGINAL_FORMAT_WATERMARK = watermark_ui.format_watermark_caption\n",
):
    if old not in text:
        raise RuntimeError(f"Missing original UI alias: {old!r}")
    text = text.replace(old, "", 1)
start = text.index("def _draft_watermark_keyboard(")
end = text.index("async def _defer_krita_start(")
text = text[:start] + text[end:]
text = text.replace(
    "_draft_watermark_caption(item, status_text=status)",
    "watermark_ui.format_watermark_caption(item, status_text=status)",
)
text = text.replace(
    "_draft_watermark_caption(item)",
    "watermark_ui.format_watermark_caption(item)",
)
text = text.replace(
    "reply_markup=_draft_watermark_keyboard(item)",
    "reply_markup=watermark_ui.build_watermark_keyboard(item)",
)
patch_block = """    watermark_ui.build_watermark_keyboard = _draft_watermark_keyboard
    watermark_ui.format_watermark_caption = _draft_watermark_caption
    core_watermark.build_watermark_keyboard = _draft_watermark_keyboard
    core_watermark.format_watermark_caption = _draft_watermark_caption
    core_watermark._wake_krita = _defer_krita_start

    from velvet_bot.domains.watermark import service as watermark_service_module

    watermark_service_module.build_watermark_keyboard = _draft_watermark_keyboard
    watermark_service_module.format_watermark_caption = _draft_watermark_caption
    watermark_actions.build_watermark_keyboard = _draft_watermark_keyboard
    watermark_actions.format_watermark_caption = _draft_watermark_caption
    watermark_actions._wake_krita = _defer_krita_start
"""
if patch_block not in text:
    raise RuntimeError("Missing watermark runtime UI patch block")
text = text.replace(patch_block, "", 1)
controller.write_text(text, encoding="utf-8")

commands_test = Path("tests/test_workspace_commands_and_watermark_drafts.py")
text = commands_test.read_text(encoding="utf-8")
text = text.replace(
    """from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_product_experience import (
    _SHOW_BUTTON_HINTS,
    _draft_watermark_keyboard,
    _home_keyboard_with_hint_toggle,
    _workspace_callback_with_template,
    _workspace_commands,
)
""",
    """from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_product_experience import (
    _SHOW_BUTTON_HINTS,
    _home_keyboard_with_hint_toggle,
    _workspace_callback_with_template,
    _workspace_commands,
)
from velvet_bot.watermark_ui import build_watermark_keyboard
""",
)
text = text.replace(
    "_draft_watermark_keyboard(_watermark_item(\"draft\"))",
    "build_watermark_keyboard(_watermark_item(\"draft\"))",
)
text = text.replace(
    "_draft_watermark_keyboard(_watermark_item(\"processing\"))",
    "build_watermark_keyboard(_watermark_item(\"processing\"))",
)
commands_test.write_text(text, encoding="utf-8")
