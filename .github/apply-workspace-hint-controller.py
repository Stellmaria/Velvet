from pathlib import Path

path = Path(
    "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
    "workspace_product_experience.py"
)
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one controller block, found {count}: {old[:90]!r}")
    text = text.replace(old, new, 1)


replace_once("from typing import Any, cast\n", "from typing import Any\n")
replace_once(
    """def _database_from_product_service(service: WorkspaceProductService) -> Database:
    database = getattr(service._workspaces, \"_database\", None)
    if database is None:
        raise RuntimeError(\"Workspace repository does not expose its database boundary.\")
    return cast(Database, database)


async def _show_button_hints(database: Database, workspace_id: int) -> bool:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            \"\"\"
            SELECT show_button_hints
            FROM workspace_settings
            WHERE workspace_id = $1::BIGINT
            \"\"\",
            int(workspace_id),
        )
    return True if value is None else bool(value)


""",
    "",
)
replace_once(
    """    database = _database_from_product_service(workspace_product_service)
    token = _SHOW_BUTTON_HINTS.set(
        await _show_button_hints(database, workspace.id)
    )
""",
    """    token = _SHOW_BUTTON_HINTS.set(
        await workspace_product_service.get_button_hints(workspace.id)
    )
""",
)
replace_once(
    """    database = _database_from_product_service(workspace_product_service)
    async with database.acquire() as connection:
        row = await connection.fetchrow(
            \"\"\"
            UPDATE workspace_settings
            SET show_button_hints = NOT show_button_hints,
                updated_at = NOW()
            WHERE workspace_id = $1::BIGINT
            RETURNING show_button_hints
            \"\"\",
            workspace.id,
        )
    if row is None:
        if isinstance(callback.message, Message):
            await callback.message.answer(\"Настройки пространства не найдены.\")
        return

    modules = await workspace_product_service.list_modules(
        workspace_id=workspace.id,
        actor_user_id=user_id,
        global_owner=_is_global_owner(user_id),
    )
    settings = await workspace_product_service._workspaces.get_settings(workspace.id)
    if settings is None or not isinstance(callback.message, Message):
        return
""",
    """    try:
        show_button_hints = await workspace_product_service.toggle_button_hints(
            workspace.id
        )
        settings = await workspace_product_service.get_settings(workspace.id)
    except ValueError as error:
        if isinstance(callback.message, Message):
            await callback.message.answer(str(error))
        return

    modules = await workspace_product_service.list_modules(
        workspace_id=workspace.id,
        actor_user_id=user_id,
        global_owner=_is_global_owner(user_id),
    )
    if not isinstance(callback.message, Message):
        return
""",
)
replace_once(
    """    token = _SHOW_BUTTON_HINTS.set(bool(row[\"show_button_hints\"]))
""",
    """    token = _SHOW_BUTTON_HINTS.set(show_button_hints)
""",
)

path.write_text(text, encoding="utf-8")
