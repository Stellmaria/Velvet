from pathlib import Path

path = Path(".github/apply-workspace-home-presentation-contracts.py")
text = path.read_text(encoding="utf-8")
old = '''replace_once(
    owner_controls,
    ''' + "'''" + '''    settings = await workspace_product_service._workspaces.get_settings(workspace.id)
    if settings is None:
        await callback.answer("Настройки пространства не найдены.", show_alert=True)
        return
''' + "'''" + ''',
    ''' + "'''" + '''    try:
        settings = await workspace_product_service.get_settings(workspace.id)
        show_button_hints = await workspace_product_service.get_button_hints(
            workspace.id
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
''' + "'''" + ''',
)
'''
new = '''old_owner_settings = ''' + "'''" + '''    settings = await workspace_product_service._workspaces.get_settings(workspace.id)
    if settings is None:
        await callback.answer("Настройки пространства не найдены.", show_alert=True)
        return
''' + "'''" + '''
new_owner_settings = ''' + "'''" + '''    try:
        settings = await workspace_product_service.get_settings(workspace.id)
        show_button_hints = await workspace_product_service.get_button_hints(
            workspace.id
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
''' + "'''" + '''
text = owner_controls.read_text(encoding="utf-8")
if text.count(old_owner_settings) != 2:
    raise RuntimeError("Expected owner and member private settings blocks")
owner_controls.write_text(
    text.replace(old_owner_settings, new_owner_settings, 1),
    encoding="utf-8",
)
'''
if old not in text:
    raise RuntimeError("Target transformation block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
