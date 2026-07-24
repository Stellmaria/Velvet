from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one block in {path}, found {count}: {old[:90]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


repository = Path("velvet_bot/domains/workspaces/product_repository.py")
replace_once(
    repository,
    """        return int(value) if value is not None else DEFAULT_WORKSPACE_ID

    async def initialize_modules(
""",
    """        return int(value) if value is not None else DEFAULT_WORKSPACE_ID

    async def get_button_hints(self, workspace_id: int) -> bool:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                \"\"\"
                SELECT show_button_hints
                FROM workspace_settings
                WHERE workspace_id = $1::BIGINT
                \"\"\",
                int(workspace_id),
            )
        return True if value is None else bool(value)

    async def toggle_button_hints(self, workspace_id: int) -> bool | None:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                \"\"\"
                UPDATE workspace_settings
                SET show_button_hints = NOT show_button_hints,
                    updated_at = NOW()
                WHERE workspace_id = $1::BIGINT
                RETURNING show_button_hints
                \"\"\",
                int(workspace_id),
            )
        return bool(value) if value is not None else None

    async def initialize_modules(
""",
)

service = Path("velvet_bot/domains/workspaces/product_service.py")
replace_once(
    service,
    """    async def get_settings(self, workspace_id: int) -> WorkspaceSettings:
        settings = await self._workspaces.get_settings(int(workspace_id))
        if settings is None:
            raise ValueError(\"Настройки пространства не найдены.\")
        return settings

    async def list_channels(self, workspace_id: int) -> tuple[WorkspaceChannel, ...]:
""",
    """    async def get_settings(self, workspace_id: int) -> WorkspaceSettings:
        settings = await self._workspaces.get_settings(int(workspace_id))
        if settings is None:
            raise ValueError(\"Настройки пространства не найдены.\")
        return settings

    async def get_button_hints(self, workspace_id: int) -> bool:
        return await self._product.get_button_hints(int(workspace_id))

    async def toggle_button_hints(self, workspace_id: int) -> bool:
        value = await self._product.toggle_button_hints(int(workspace_id))
        if value is None:
            raise ValueError(\"Настройки пространства не найдены.\")
        return value

    async def list_channels(self, workspace_id: int) -> tuple[WorkspaceChannel, ...]:
""",
)
