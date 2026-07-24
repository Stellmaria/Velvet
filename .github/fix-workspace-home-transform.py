from pathlib import Path

path = Path(".github/apply-workspace-home-presentation-contracts.py")
text = path.read_text(encoding="utf-8")

settings_old = """replace_once(
    owner_controls,
    '''    settings = await workspace_product_service._workspaces.get_settings(workspace.id)
    if settings is None:
        await callback.answer(\"Настройки пространства не найдены.\", show_alert=True)
        return
''',
    '''    try:
        settings = await workspace_product_service.get_settings(workspace.id)
        show_button_hints = await workspace_product_service.get_button_hints(
            workspace.id
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
''',
)
"""
settings_new = """old_owner_settings = '''    settings = await workspace_product_service._workspaces.get_settings(workspace.id)
    if settings is None:
        await callback.answer(\"Настройки пространства не найдены.\", show_alert=True)
        return
'''
new_owner_settings = '''    try:
        settings = await workspace_product_service.get_settings(workspace.id)
        show_button_hints = await workspace_product_service.get_button_hints(
            workspace.id
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
'''
text = owner_controls.read_text(encoding=\"utf-8\")
if text.count(old_owner_settings) != 2:
    raise RuntimeError(\"Expected owner and member private settings blocks\")
owner_controls.write_text(
    text.replace(old_owner_settings, new_owner_settings, 1),
    encoding=\"utf-8\",
)
"""
if settings_old not in text:
    raise RuntimeError("Settings transformation block not found")
text = text.replace(settings_old, settings_new, 1)

keyboard_old = """text = owner_controls.read_text(encoding=\"utf-8\")
old_keyboard_call = '''                modules=modules,
            ),
'''
new_keyboard_call = '''                modules=modules,
                show_button_hints=show_button_hints,
            ),
'''
if text.count(old_keyboard_call) < 2:
    raise RuntimeError(\"Missing owner home keyboard calls\")
text = text.replace(old_keyboard_call, new_keyboard_call, 2)
"""
keyboard_new = """text = owner_controls.read_text(encoding=\"utf-8\")
owner_keyboard_call = '''            reply_markup=_workspace_home_keyboard(
                workspace,
                public_enabled=settings.public_archive_enabled,
                modules=modules,
            ),
'''
owner_keyboard_with_hints = '''            reply_markup=_workspace_home_keyboard(
                workspace,
                public_enabled=settings.public_archive_enabled,
                modules=modules,
                show_button_hints=show_button_hints,
            ),
'''
owner_fallback_call = '''                reply_markup=_workspace_home_keyboard(
                    workspace,
                    public_enabled=settings.public_archive_enabled,
                    modules=modules,
                ),
'''
owner_fallback_with_hints = '''                reply_markup=_workspace_home_keyboard(
                    workspace,
                    public_enabled=settings.public_archive_enabled,
                    modules=modules,
                    show_button_hints=show_button_hints,
                ),
'''
if owner_keyboard_call not in text or owner_fallback_call not in text:
    raise RuntimeError(\"Missing owner home keyboard calls\")
text = text.replace(owner_keyboard_call, owner_keyboard_with_hints, 1)
text = text.replace(owner_fallback_call, owner_fallback_with_hints, 1)
"""
if keyboard_old not in text:
    raise RuntimeError("Keyboard transformation block not found")
text = text.replace(keyboard_old, keyboard_new, 1)

path.write_text(text, encoding="utf-8")
