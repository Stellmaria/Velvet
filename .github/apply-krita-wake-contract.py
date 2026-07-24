from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one block in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


supervisor = Path("velvet_bot/krita_supervisor.py")
replace_once(
    supervisor,
    """from __future__ import annotations

from typing import Any

from velvet_bot.supervisor_client import SupervisorClient, build_supervisor_client
""",
    """from __future__ import annotations

import logging
from typing import Any

from velvet_bot.supervisor_client import (
    SupervisorClient,
    SupervisorClientError,
    build_supervisor_client,
)

logger = logging.getLogger(__name__)
""",
)
replace_once(
    supervisor,
    """def build_krita_supervisor_client() -> KritaSupervisorClient | None:
    base = build_supervisor_client()
    if base is None:
        return None
    return KritaSupervisorClient(
        base_url=base.base_url,
        token=base.token,
        timeout_seconds=base.timeout_seconds,
    )


__all__ = ("KritaSupervisorClient", "build_krita_supervisor_client")
""",
    """def build_krita_supervisor_client() -> KritaSupervisorClient | None:
    base = build_supervisor_client()
    if base is None:
        return None
    return KritaSupervisorClient(
        base_url=base.base_url,
        token=base.token,
        timeout_seconds=base.timeout_seconds,
    )


async def wake_krita(*, context: str = "watermark") -> str | None:
    client = build_krita_supervisor_client()
    if client is None:
        return None
    try:
        await client.ensure_krita()
    except SupervisorClientError as error:
        logger.warning("Could not wake Krita for %s: %s", context, error)
        return str(error)
    return None


__all__ = (
    "KritaSupervisorClient",
    "build_krita_supervisor_client",
    "wake_krita",
)
""",
)

core = Path(
    "velvet_bot/presentation/telegram/routers/core_operations_controllers/watermark.py"
)
text = core.read_text(encoding="utf-8")
text = text.replace(
    "from velvet_bot.krita_supervisor import build_krita_supervisor_client\n",
    "from velvet_bot.krita_supervisor import wake_krita\n",
    1,
)
text = text.replace("from velvet_bot.supervisor_client import SupervisorClientError\n", "", 1)
start = text.index("async def _wake_krita()")
end = text.index("class WatermarkInputReplyFilter")
text = text[:start] + text[end:]
old = """    wake_error = await _wake_krita()
    if wake_error:
        await message.answer(
            "⚠️ Не удалось автоматически запустить Krita. "
            "Задание будет создано, но Krita нужно открыть вручную.\n\n"
            f"<code>{escape(wake_error[:800])}</code>"
        )

"""
if old not in text:
    raise RuntimeError("Missing early Krita wake in job creation")
text = text.replace(old, "", 1)
text = text.replace(
    "format_watermark_caption(item, status_text=\"поставлено в очередь\")",
    "format_watermark_caption(item)",
    1,
)
old = """    if source is None:
        wake_error = await _wake_krita()
        warning = (
            f"\n\n⚠️ Автозапуск Krita: <code>{escape(wake_error[:500])}</code>"
            if wake_error
            else ""
        )
        await message.answer(
            "Ответьте командой <code>/watermark</code> на изображение. "
            "Команда является аварийным резервом; обычный вход доступен из меню."
            + warning
        )
        return
"""
new = """    if source is None:
        await message.answer(
            "Ответьте командой <code>/watermark</code> на изображение. "
            "Команда является аварийным резервом; обычный вход доступен из меню. "
            "Krita запустится только после кнопки генерации."
        )
        return
"""
if old not in text:
    raise RuntimeError("Missing watermark command wake block")
text = text.replace(old, new, 1)
text = text.replace(
    "    await _wake_krita()\n    service = _build_service(bot, database)\n",
    "    await wake_krita(context=\"watermark color revision\")\n    service = _build_service(bot, database)\n",
    1,
)
old = """    if action in {"start", "help"}:
        wake_error = await _wake_krita()
        await callback.answer()
        if isinstance(callback.message, Message):
            warning = (
                "\n\n⚠️ Krita не запустилась автоматически. Откройте её вручную.\n"
                f"<code>{escape(wake_error[:800])}</code>"
                if wake_error
                else "\n\nKrita запущена автоматически и закроется после 10 минут простоя."
            )
            await callback.message.answer(
                "<b>Водяной знак Velvet Anatomy</b>\n\n"
                "Ответьте изображением на это сообщение. Бот сохранит неизменяемый "
                "исходник, а Krita будет строить отдельные preview."
                + warning
                + f"\n\n<code>{_INPUT_MARKER}</code>",
                reply_markup=build_watermark_start_keyboard(),
            )
        return
"""
new = """    if action in {"start", "help"}:
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "<b>Водяной знак Velvet Anatomy</b>\n\n"
                "Ответьте изображением на это сообщение. Бот сохранит неизменяемый "
                "исходник. Сначала настройте черновик; Krita запустится только после "
                "кнопки «Сгенерировать preview»."
                f"\n\n<code>{_INPUT_MARKER}</code>",
                reply_markup=build_watermark_start_keyboard(),
            )
        return
"""
if old not in text:
    raise RuntimeError("Missing start/help Krita wake block")
text = text.replace(old, new, 1)
text = text.replace(
    """    if action != "cancel":
        await _wake_krita()
""",
    """    if action != "cancel":
        await wake_krita(context="watermark revision")
""",
    1,
)
core.write_text(text, encoding="utf-8")

public_actions = Path(
    "velvet_bot/presentation/telegram/routers/public_archive/watermark_actions.py"
)
text = public_actions.read_text(encoding="utf-8")
text = text.replace(
    "from velvet_bot.krita_supervisor import build_krita_supervisor_client\n",
    "from velvet_bot.krita_supervisor import wake_krita\n",
    1,
)
text = text.replace("from velvet_bot.supervisor_client import SupervisorClientError\n", "", 1)
start = text.index("async def _wake_krita()")
end = text.index("def _source_suffix")
text = text[:start] + text[end:]
text = text.replace(
    "wake_error = await _wake_krita()",
    'wake_error = await wake_krita(context="public archive watermark")',
    1,
)
public_actions.write_text(text, encoding="utf-8")

controller = Path(
    "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
    "workspace_product_experience.py"
)
text = controller.read_text(encoding="utf-8")
if "from velvet_bot.krita_supervisor import wake_krita\n" not in text:
    text = text.replace(
        "from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService\n",
        "from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService\n"
        "from velvet_bot.krita_supervisor import wake_krita\n",
        1,
    )
text = text.replace("_ORIGINAL_CORE_WAKE_KRITA = core_watermark._wake_krita\n", "", 1)
old = """async def _defer_krita_start() -> str | None:
    return None


"""
if old not in text:
    raise RuntimeError("Missing deferred Krita helper")
text = text.replace(old, "", 1)
text = text.replace(
    "wake_error = await _ORIGINAL_CORE_WAKE_KRITA()",
    'wake_error = await wake_krita(context="workspace watermark preview")',
    1,
)
controller.write_text(text, encoding="utf-8")
