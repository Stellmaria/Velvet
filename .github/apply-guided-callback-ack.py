from pathlib import Path

path = Path("velvet_bot/presentation/telegram/routers/workspace_guided_actions.py")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one guided callback block, found {count}: {old[:80]!r}")
    text = text.replace(old, new, 1)


replace_once(
    """    answer: str | None = None,
    show_alert: bool = False,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer(\"Меню больше недоступно.\", show_alert=True)
        return
""",
    """    answer: str | None = None,
    show_alert: bool = False,
    acknowledge: bool = True,
) -> None:
    if not isinstance(callback.message, Message):
        if acknowledge:
            await callback.answer(\"Меню больше недоступно.\", show_alert=True)
        return
""",
)
replace_once(
    """    await callback.answer(answer, show_alert=show_alert)


async def _resolve_workspace(
""",
    """    if acknowledge:
        await callback.answer(answer, show_alert=show_alert)


async def _resolve_workspace(
""",
)
replace_once(
    """async def _render_quick(
    callback: CallbackQuery,
    *,
    workspace: Workspace,
    user_id: int,
    workspace_product_service: WorkspaceProductService,
) -> None:
""",
    """async def _render_quick(
    callback: CallbackQuery,
    *,
    workspace: Workspace,
    user_id: int,
    workspace_product_service: WorkspaceProductService,
    acknowledge: bool = True,
) -> None:
""",
)
replace_once(
    """        reply_markup=_quick_keyboard(workspace.id, enabled),
    )


def _connections_keyboard(
""",
    """        reply_markup=_quick_keyboard(workspace.id, enabled),
        acknowledge=acknowledge,
    )


def _connections_keyboard(
""",
)
replace_once(
    """async def _start_category(
    callback: CallbackQuery,
    *,
    state: FSMContext,
    workspace: Workspace,
) -> None:
""",
    """async def _start_category(
    callback: CallbackQuery,
    *,
    state: FSMContext,
    workspace: Workspace,
    acknowledge: bool = True,
) -> None:
""",
)
replace_once(
    """            \"Отправьте понятное название категории. Технический ключ бот создаст сам.\"
        ),
        reply_markup=_taxonomy_prompt_keyboard(workspace.id),
    )


async def _start_universe(
""",
    """            \"Отправьте понятное название категории. Технический ключ бот создаст сам.\"
        ),
        reply_markup=_taxonomy_prompt_keyboard(workspace.id),
        acknowledge=acknowledge,
    )


async def _start_universe(
""",
)
replace_once(
    """async def _start_universe(
    callback: CallbackQuery,
    *,
    state: FSMContext,
    workspace: Workspace,
) -> None:
""",
    """async def _start_universe(
    callback: CallbackQuery,
    *,
    state: FSMContext,
    workspace: Workspace,
    acknowledge: bool = True,
) -> None:
""",
)
replace_once(
    """            \"Отправьте название вселенной. Технический ключ бот создаст сам.\"
        ),
        reply_markup=_taxonomy_prompt_keyboard(workspace.id),
    )


async def _start_story(
""",
    """            \"Отправьте название вселенной. Технический ключ бот создаст сам.\"
        ),
        reply_markup=_taxonomy_prompt_keyboard(workspace.id),
        acknowledge=acknowledge,
    )


async def _start_story(
""",
)
replace_once(
    """    workspace: Workspace,
    workspace_product_service: WorkspaceProductService,
) -> None:
    universes = await workspace_product_service.list_universes(workspace.id)
    if not universes:
        await callback.answer(\"Сначала создайте хотя бы одну вселенную.\", show_alert=True)
        return
""",
    """    workspace: Workspace,
    workspace_product_service: WorkspaceProductService,
    acknowledge: bool = True,
) -> None:
    universes = await workspace_product_service.list_universes(workspace.id)
    if not universes:
        if acknowledge:
            await callback.answer(\"Сначала создайте хотя бы одну вселенную.\", show_alert=True)
        elif isinstance(callback.message, Message):
            await callback.message.answer(\"Сначала создайте хотя бы одну вселенную.\")
        return
""",
)
replace_once(
    """        text=\"<b>➕ Новая история</b>\\n\\nВыберите вселенную истории.\",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(WorkspaceCallback.filter(F.action == \"quick\"))
""",
    """        text=\"<b>➕ Новая история</b>\\n\\nВыберите вселенную истории.\",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        acknowledge=acknowledge,
    )


@router.callback_query(WorkspaceCallback.filter(F.action == \"quick\"))
""",
)
replace_once(
    """    try:
        await state.clear()
        workspace = await _resolve_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=callback.from_user.id,
            workspace_service=workspace_service,
        )
        await _render_quick(
            callback,
            workspace=workspace,
            user_id=callback.from_user.id,
            workspace_product_service=workspace_product_service,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
""",
    """    try:
        workspace = await _resolve_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=callback.from_user.id,
            workspace_service=workspace_service,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer()
    await state.clear()
    await _render_quick(
        callback,
        workspace=workspace,
        user_id=callback.from_user.id,
        workspace_product_service=workspace_product_service,
        acknowledge=False,
    )
""",
)
replace_once(
    """    try:
        workspace = await _resolve_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=callback.from_user.id,
            workspace_service=workspace_service,
        )
        if callback_data.action == \"addcategory\":
            await _start_category(callback, state=state, workspace=workspace)
        elif callback_data.action == \"adduniverse\":
            await _start_universe(callback, state=state, workspace=workspace)
        else:
            await _start_story(
                callback,
                state=state,
                workspace=workspace,
                workspace_product_service=workspace_product_service,
            )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
""",
    """    try:
        workspace = await _resolve_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=callback.from_user.id,
            workspace_service=workspace_service,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer()
    if callback_data.action == \"addcategory\":
        await _start_category(
            callback, state=state, workspace=workspace, acknowledge=False
        )
    elif callback_data.action == \"adduniverse\":
        await _start_universe(
            callback, state=state, workspace=workspace, acknowledge=False
        )
    else:
        await _start_story(
            callback,
            state=state,
            workspace=workspace,
            workspace_product_service=workspace_product_service,
            acknowledge=False,
        )
""",
)

path.write_text(text, encoding="utf-8")
