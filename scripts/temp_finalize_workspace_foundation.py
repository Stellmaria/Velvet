from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> None:
    old_migration = ROOT / "migrations/102_workspaces.sql"
    new_migration = ROOT / "migrations/103_workspaces.sql"
    if not old_migration.is_file():
        raise RuntimeError("Workspace migration source is missing")
    old_migration.replace(new_migration)

    replace_once(
        ROOT / "tests/test_workspace_foundation.py",
        'ROOT / "migrations/102_workspaces.sql"',
        'ROOT / "migrations/103_workspaces.sql"',
    )
    replace_once(
        ROOT / "tests/test_p3e_repository_layout_inventory.py",
        'self.assertEqual(31, inventory["repository_module_count"])',
        'self.assertEqual(32, inventory["repository_module_count"])',
    )
    replace_once(
        ROOT / "tests/test_p3e_repository_layout_inventory.py",
        'self.assertEqual(30, inventory["layout_counts"]["domain"])',
        'self.assertEqual(31, inventory["layout_counts"]["domain"])',
    )

    worklog = ROOT / "docs/worklog/2026-07-21-workspace-foundation.md"
    worklog.write_text(
        '''# Сессия: Workspace foundation

- Дата: 2026-07-21
- ID: `2026-07-21-workspace-foundation`
- Линия/фаза: multi-workspace foundation
- Статус: `частично`
- Ветка: `agent/workspace-foundation`
- Базовый commit: `3b38844fd57cb4ff18e3c8de5710facdef394e69`

## Перед началом

### Цель

Заложить безопасный фундамент для отдельных пользовательских архивов без пересечения с пространством Стэл: рабочие пространства, роли участников, настройки Telegram-каналов и изоляция персонажей по `workspace_id`.

### Исходный контекст

Текущая модель была однопользовательской. Персонажи имели глобально уникальный `normalized_name`, каналы загружались из глобального `.env`, а роли owner/moderator не были привязаны к отдельному архиву. Простое добавление нового user ID не создавало изоляцию данных.

### Планируемый объём

- миграция `workspaces`, `workspace_members`, `workspace_settings`, `workspace_channels`;
- создание системного пространства Velvet и перенос существующих персонажей в него;
- добавление `workspace_id` в `characters`;
- уникальность имени персонажа внутри workspace;
- domain models/repository/service для workspace;
- безопасный resolver пространства пользователя;
- тесты миграции, ролей, настроек и недоступности чужого workspace;
- контракт следующей фазы для перевода archive queries на обязательный workspace context.

### Критерии готовности

- существующие данные автоматически принадлежат системному workspace;
- один и тот же персонаж может существовать в разных пространствах;
- пользователь получает только workspace, участником которого является;
- роли ограничены `owner/admin/editor/reviewer/viewer`;
- Telegram chat IDs и ссылки хранятся отдельно для каждого пространства;
- схема не открывает доступ к owner-only Supervisor/GitHub/Codex;
- полный CI зелёный.

### Риски и ограничения

Это первая фаза. Она создаёт tenant boundary и переносит ownership персонажей, но не включает внешнему пользователю production-меню до завершения сквозного перевода archive/publication/Qwen запросов на `workspace_id`. Такой порядок намеренно консервативен: сначала изоляция, потом кнопки.

## После завершения

### Фактически сделано

- добавлены `workspaces`, `workspace_members`, `workspace_settings` и `workspace_channels`;
- системное пространство Velvet закреплено за ID `1`;
- существующие персонажи мигрируют в системное пространство;
- глобальная уникальность имени заменена на `UNIQUE (workspace_id, normalized_name)`;
- `Database.create_character`, поиск, topic binding и списки получили совместимый `workspace_id=1` по умолчанию;
- `CharacterDirectoryRepository` фильтрует чтение и изменение по workspace;
- добавлены роли `owner/admin/editor/reviewer/viewer` и явный global-owner support bypass;
- настройки каналов, публичного архива, скачиваний, Qwen и часового пояса хранятся отдельно;
- добавлены unit и PostgreSQL isolation tests;
- generated repository-layout и Telegram navigation inventories обновлены.

### Миграции и совместимость

Новая миграция: `103_workspaces.sql`. Старые вызовы без workspace продолжают работать в системном пространстве ID `1`. Существующие персонажи, медиа и topic links сохраняются. Внешний пользовательский интерфейс пока не включён, поэтому частично переведённые домены не могут быть использованы для обхода tenant boundary.

### Проверки

Первый CI на head `3f24849161775feedba23bf925d6d4b974541f13` подтвердил успешные type-check и Docker build. Tests и restore drill корректно остановились из-за занятого номера миграции `102`; дополнительно generated P3E/navigation baselines потребовали регенерации. Исправления внесены, запускается повторный полный CI.

### PR и commit

PR #275: `Add workspace foundation for isolated personal archives`. Implementation head до исправления контрактов: `3f24849161775feedba23bf925d6d4b974541f13`.

### Незавершённое

- archive/public archive, stories, references, publication, Qwen, subscriptions и analytics ещё не переведены сквозным образом на workspace context;
- мастер подключения каналов и внешнее меню не включены;
- active workspace selection в Telegram FSM не добавлен.

### Следующий шаг

Перевести archive/public archive read/write boundaries на обязательный workspace context, затем добавить выбор активного пространства и мастер проверки прав бота в пользовательских каналах.
''',
        encoding="utf-8",
    )

    run(
        sys.executable,
        "scripts/inventory_repository_layout.py",
        "--write",
        "--label",
        "p3e-repository-layout-complete",
    )
    run(
        sys.executable,
        "scripts/telegram_navigation_inventory.py",
        "--root",
        "velvet_bot",
        "--markdown",
        "docs/generated/telegram_navigation_inventory.md",
        "--check",
    )

    (ROOT / "scripts/temp_finalize_workspace_foundation.py").unlink()
    (ROOT / ".github/workflows/temp-finalize-workspace-foundation.yml").unlink()


if __name__ == "__main__":
    main()
