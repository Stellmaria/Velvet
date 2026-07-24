from pathlib import Path

path = Path("velvet_bot/presentation/telegram/routers/workspace_reference_buttons.py")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one reference callback block, found {count}: {old[:80]!r}")
    text = text.replace(old, new, 1)


replace_once(
    """async def _edit_reference_page(
    callback: CallbackQuery,
    *,
    page,
) -> None:
    if page.reference is None:
        await callback.answer(\"Референсы больше не найдены.\", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer(\"Сообщение больше недоступно.\", show_alert=True)
        return
""",
    """async def _send_manage_notice(callback: CallbackQuery, text: str) -> None:
    if isinstance(callback.message, Message):
        await callback.message.answer(text)


async def _edit_reference_page(
    callback: CallbackQuery,
    *,
    page,
    acknowledge: bool = True,
) -> None:
    if page.reference is None:
        if acknowledge:
            await callback.answer(\"Референсы больше не найдены.\", show_alert=True)
        else:
            await _send_manage_notice(callback, \"Референсы больше не найдены.\")
        return
    if not isinstance(callback.message, Message):
        if acknowledge:
            await callback.answer(\"Сообщение больше недоступно.\", show_alert=True)
        return
""",
)
replace_once(
    """    await callback.answer()


class PendingReferenceReplaceFilter(BaseFilter):
""",
    """    if acknowledge:
        await callback.answer()


class PendingReferenceReplaceFilter(BaseFilter):
""",
)
replace_once(
    """    if await _reject_access(callback, personal_reference_context):
        return
    action = callback_data.action
""",
    """    if await _reject_access(callback, personal_reference_context):
        return
    await callback.answer()
    action = callback_data.action
""",
)
replace_once(
    """        await callback.answer()
        return
    if action in {\"manage_upload_done\", \"manage_upload_cancel\"}:
""",
    """        return
    if action in {\"manage_upload_done\", \"manage_upload_cancel\"}:
""",
)
replace_once(
    """        if stopped is None:
            await callback.answer(\"Активной загрузки референсов нет.\", show_alert=True)
            return
""",
    """        if stopped is None:
            await _send_manage_notice(callback, \"Активной загрузки референсов нет.\")
            return
""",
)
replace_once(
    """        await callback.answer(text, show_alert=True)
        return
    if action == \"manage_back\":
""",
    """        await _send_manage_notice(callback, text)
        return
    if action == \"manage_back\":
""",
)
replace_once(
    """        await callback.answer()
        return

    page = await get_reference_page(
""",
    """        return

    page = await get_reference_page(
""",
)
replace_once(
    """    if page is None:
        await callback.answer(\"Персонаж не найден в активном пространстве.\", show_alert=True)
        return
""",
    """    if page is None:
        await _send_manage_notice(callback, \"Персонаж не найден в активном пространстве.\")
        return
""",
)
replace_once(
    """        except WorkspaceAccessError as error:
            await callback.answer(str(error), show_alert=True)
            return
""",
    """        except WorkspaceAccessError as error:
            await _send_manage_notice(callback, str(error))
            return
""",
)
replace_once(
    """        await callback.answer()
        return
    if page.reference is None:
        await callback.answer(\"У персонажа пока нет референсов.\", show_alert=True)
        return
    if action == \"manage_show\":
        await _edit_reference_page(callback, page=page)
        return
""",
    """        return
    if page.reference is None:
        await _send_manage_notice(callback, \"У персонажа пока нет референсов.\")
        return
    if action == \"manage_show\":
        await _edit_reference_page(callback, page=page, acknowledge=False)
        return
""",
)
replace_once(
    """    if action == \"manage_compare\":
        await callback.answer(
            f\"Ответьте на готовое изображение командой /compare_ref \"
            f\"{page.character.name} {page.offset + 1}\",
            show_alert=True,
        )
        return
""",
    """    if action == \"manage_compare\":
        await _send_manage_notice(
            callback,
            f\"Ответьте на готовое изображение командой /compare_ref \"
            f\"{page.character.name} {page.offset + 1}\",
        )
        return
""",
)
replace_once(
    """    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    if page.reference.id != callback_data.reference_id:
        await callback.answer(
            \"Список изменился. Откройте референсы заново.\",
            show_alert=True,
        )
        return
""",
    """    except WorkspaceAccessError as error:
        await _send_manage_notice(callback, str(error))
        return
    if page.reference.id != callback_data.reference_id:
        await _send_manage_notice(
            callback, \"Список изменился. Откройте референсы заново.\"
        )
        return
""",
)
for old in (
    """        await callback.answer()
        return
    if action == \"manage_delete_prompt\":
""",
    """        await callback.answer()
        return
    if action == \"manage_delete_cancel\":
""",
    """        await callback.answer()
        return
    if action == \"manage_delete\":
""",
):
    replace_once(old, old.replace("        await callback.answer()\n", ""))
replace_once(
    """        if result.reference is None:
            await callback.answer(\"Референс уже удалён.\", show_alert=True)
            return
""",
    """        if result.reference is None:
            await _send_manage_notice(callback, \"Референс уже удалён.\")
            return
""",
)
replace_once(
    """            await callback.answer(\"Референс удалён.\")
            return
""",
    """            await _send_manage_notice(callback, \"Референс удалён.\")
            return
""",
)
replace_once(
    """        if next_page is None or next_page.reference is None:
            await callback.answer(\"Не удалось открыть следующий референс.\", show_alert=True)
            return
        await _edit_reference_page(callback, page=next_page)
        return
    await callback.answer(\"Неизвестное действие.\", show_alert=True)
""",
    """        if next_page is None or next_page.reference is None:
            await _send_manage_notice(callback, \"Не удалось открыть следующий референс.\")
            return
        await _edit_reference_page(callback, page=next_page, acknowledge=False)
        return
    await _send_manage_notice(callback, \"Неизвестное действие.\")
""",
)

path.write_text(text, encoding="utf-8")
