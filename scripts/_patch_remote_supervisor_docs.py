from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env.example"
DOC = ROOT / "docs/SUPERVISOR.md"
CHANGELOG = ROOT / "CHANGELOG.md"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: ожидалось одно совпадение, найдено {count}")
    return source.replace(old, new, 1)


def patch_env() -> None:
    source = ENV.read_text(encoding="utf-8")
    source = replace_once(
        source,
        "SUPERVISOR_TEST_COMMAND=\".venv314\\Scripts\\python.exe\" -m unittest discover -s tests -v\n"
        "SUPERVISOR_AUTO_RESTART=true\n",
        "SUPERVISOR_TEST_COMMAND=\".venv314\\Scripts\\python.exe\" -m unittest discover -s tests -v\n"
        "SUPERVISOR_TASK_NAME=VelvetSupervisor\n"
        "SUPERVISOR_AUTO_RESTART=true\n",
        "env task name",
    )
    ENV.write_text(source, encoding="utf-8")


def patch_doc() -> None:
    source = DOC.read_text(encoding="utf-8")
    source = replace_once(
        source,
        "        ├── выполняет fetch/fast-forward/tests/restart\n"
        "        ├── откатывает неудачное обновление\n"
        "        └── запускает Codex в отдельном Git worktree\n",
        "        ├── выполняет fetch/fast-forward/tests/restart\n"
        "        ├── откатывает неудачное обновление\n"
        "        ├── запускает команды только из безопасного allowlist\n"
        "        ├── передаёт self-restart независимой задаче Windows\n"
        "        └── запускает Codex в отдельном Git worktree\n",
        "architecture additions",
    )
    source = replace_once(
        source,
        "В разделе `Supervisor и Codex` доступны четыре экрана:\n",
        "В разделе `Supervisor и Codex` доступны шесть экранов:\n",
        "screen count",
    )
    marker = "### Codex\n\n"
    added = '''### Безопасная консоль

Экран `🖥 Консоль` не является произвольным PowerShell. Текст пользователя
сопоставляется с точным allowlist, а выполнение всегда происходит как argv с
`shell=False` и фиксированным рабочим каталогом проекта.

Перед запуском Supervisor показывает:

- точную команду;
- каталог проекта;
- таймаут;
- инициатора;
- одноразовый ID подтверждения.

Подтверждение действует десять минут и может быть использовано только один раз.
Пайпы, перенаправления, разделители команд, command substitution и неизвестные
команды отклоняются до запуска. Вывод ограничивается по размеру, а токены, URL
базы и другие секреты маскируются.

В реестр входят диагностические операции Git, Python, тестов, Ollama, процессов
и Windows-задачи. Команды, изменяющие Git или жизненный цикл Supervisor,
реализованы отдельными типизированными операциями, а не произвольным shell.

### Сам Supervisor

Экран `🧩 Сам Supervisor` умеет:

- перезапустить Supervisor и дочерний бот;
- выполнить безопасный self-update `main` и перезапуститься;
- показать результат последней bootstrap-операции.

Текущий процесс не пытается перезапустить сам себя. Он создаёт одноразовую задачу
Windows `VelvetSupervisorBootstrap-<operation_id>`, отвечает Telegram и передаёт
операцию внешнему helper. Helper завершает старые PID, при необходимости делает
только fast-forward update, запускает полный набор тестов, восстанавливает
предыдущий commit при ошибке и поднимает основную задачу `VelvetSupervisor`.
Результат сохраняется в `runtime/supervisor/bootstrap-result.json` и отправляется
в служебный Telegram-чат независимо от остановленного процесса.

Настройка имени основной задачи:

```env
SUPERVISOR_TASK_NAME=VelvetSupervisor
```

'''
    source = replace_once(source, marker, added + marker, "remote sections")
    source = replace_once(
        source,
        "Старые команды `/supervisor`, `/logs`, `/restart`, `/update`, `/rollback`,\n"
        "`/codex` и `/codex_status` сохранены в обработчиках только как аварийный резерв.\n",
        "Старые команды `/supervisor`, `/logs`, `/restart`, `/update`, `/rollback`,\n"
        "`/codex`, `/codex_status`, `/console` и `/supervisor_self` сохранены в\n"
        "обработчиках только как аварийный резерв.\n",
        "reserve commands",
    )
    source = replace_once(
        source,
        "SUPERVISOR_COMMAND_TIMEOUT_SECONDS=900\n"
        "SUPERVISOR_UPDATE_REMOTE=origin\n",
        "SUPERVISOR_COMMAND_TIMEOUT_SECONDS=900\n"
        "SUPERVISOR_TASK_NAME=VelvetSupervisor\n"
        "SUPERVISOR_UPDATE_REMOTE=origin\n",
        "settings task name",
    )
    DOC.write_text(source, encoding="utf-8")


def patch_changelog() -> None:
    source = CHANGELOG.read_text(encoding="utf-8")
    source = replace_once(
        source,
        "- автоматическая проверка соответствия всех literal `quality:` callbacks реальным handlers.\n",
        "- автоматическая проверка соответствия всех literal `quality:` callbacks реальным handlers;\n"
        "- безопасная удалённая консоль Supervisor с allowlist, preview, подтверждением, таймаутами и аудитом;\n"
        "- внешний Windows bootstrap для удалённого перезапуска и self-update самого Supervisor.\n",
        "changelog added",
    )
    source = replace_once(
        source,
        "- кнопка ручного запуска worker подтверждает нажатие до выполнения длительного цикла.\n",
        "- кнопка ручного запуска worker подтверждает нажатие до выполнения длительного цикла;\n"
        "- Supervisor показывает отдельные экраны `Консоль` и `Сам Supervisor`;\n"
        "- команды удалённой диагностики выполняются без shell из фиксированного каталога с маскированием секретов.\n",
        "changelog changed",
    )
    CHANGELOG.write_text(source, encoding="utf-8")


def main() -> None:
    patch_env()
    patch_doc()
    patch_changelog()


if __name__ == "__main__":
    main()
