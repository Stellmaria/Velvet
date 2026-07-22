from __future__ import annotations

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"finish marker not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "tests/test_p3_architecture_organization.py",
    '''    "velvet_bot.presentation.telegram.routers.workspace_reference_library",
    "velvet_bot.presentation.telegram.routers.workspaces",''',
    '''    "velvet_bot.presentation.telegram.routers.workspace_reference_library",
    "velvet_bot.presentation.telegram.routers.workspace_team",
    "velvet_bot.presentation.telegram.routers.workspace_watermark",
    "velvet_bot.presentation.telegram.routers.workspaces",''',
)

readme = Path("tools/krita/README.md")
readme.write_text(
    readme.read_text(encoding="utf-8")
    + """

## Пользовательские логотипы workspace

Bridge schema v2 принимает snapshot логотипа из `assets/`. Поддерживаются очищенный SVG и прозрачный PNG. Файл обязан находиться внутри bridge-каталога; плагин не читает внешние URL и не меняет исходник. Цветовые настройки применяются только к встроенному логотипу Velvet, пользовательский asset сохраняет собственные цвета.
""",
    encoding="utf-8",
)
docs = Path("docs/krita_watermark.md")
docs.write_text(
    docs.read_text(encoding="utf-8")
    + """

## Логотип пространства

Владелец или администратор личного workspace может загрузить SVG либо PNG/WebP с прозрачным фоном через модуль `💧 Watermark`. SVG очищается от scripts, event handlers, `DOCTYPE`, entities и внешних ресурсов. Raster нормализуется в RGBA PNG и обязан содержать реальные прозрачные пиксели. Каждый watermark job сохраняет snapshot выбранного файла, поэтому последующая замена логотипа не изменяет уже созданные задания.
""",
    encoding="utf-8",
)

for path in (
    ".github/workflows/tmp-wire-team-watermark.yml",
    "tools/tmp_wire_team_watermark.py",
    "tools/tmp_wire_team_watermark_resume.py",
    "tools/tmp_wire_team_watermark_finish.py",
):
    Path(path).unlink(missing_ok=True)
