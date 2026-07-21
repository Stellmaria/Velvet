from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"missing token in {path}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_section(path: str, start: str, end: str, replacement: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    start_index = text.find(start)
    end_index = text.find(end, start_index + len(start))
    if start_index < 0 or end_index < 0:
        raise RuntimeError(f"section markers missing in {path}: {start!r} -> {end!r}")
    target.write_text(
        text[:start_index] + replacement.rstrip() + "\n\n" + text[end_index:],
        encoding="utf-8",
    )


def update_development_status() -> None:
    path = "docs/development_status.md"
    replace_once(path, "Дата актуализации: 20 июля 2026 года.", "Дата актуализации: 21 июля 2026 года.")
    replace_once(
        path,
        "- WorkerManager, диагностика и центр ошибок;",
        "- WorkerManager, центр ошибок и owner-only диагностические ZIP-пакеты;",
    )
    replace_section(
        path,
        "## Закрытие P2 stability",
        "## P3: организация структуры",
        """## Закрытие P2 stability

Статус: завершена.

Текущий generated AST-инвентарь после owner diagnostics:

- broad exception boundaries: 76;
- approved boundaries: 76;
- unresolved boundaries: 0;
- callback handlers: 98;
- late/missing callbacks: 0;
- следующий P2-срез отсутствует.

Источник измерения: `docs/p2_stability_inventory.*`.

Широкие перехваты остались только на проверенных внешних границах подсистем с логированием, компенсацией и явным пробросом отмены.""",
    )
    replace_section(
        path,
        "## P3: организация структуры",
        "## Эксплуатационные обязательства",
        """## P3: организация структуры

Статус: основные линии P3A–P3E завершены. Следующий кодовый срез: P3F.

### P3A. Источники истины

Статус: завершено.

- status, project memory, architecture audit и changelog синхронизированы с `main`;
- кодовый долг отделён от Windows/staging/backup эксплуатационных проверок;
- generated inventories являются измеримым источником текущих чисел.

### P3B. Telegram composition

Статус: завершено.

- корневой Router подключает четыре крупные доменные bundles;
- 60 активных routers зарегистрированы без дублей;
- порядок catch-all-sensitive routers фиксируется тестом;
- прямых imports `velvet_bot.handlers.*` нет.

### P3C. Физический перенос presentation

Статус: завершено.

Все активные Telegram-контроллеры находятся в `velvet_bot/presentation/telegram/routers`. Физических legacy handler-файлов, implementations и module aliases осталось 0.

### P3D. Compatibility retirement

Статус handler compatibility: завершено.

Production legacy-consumer inventory закрыт: 0 файлов, 0 references и 0 legacy modules. Handler aliases полностью удалены. В explicit pre/post-import registry остаются 8 runtime compatibility-компонентов; их дальнейшая классификация относится к отдельной cleanup-линии и не возвращает старые handler paths.

### P3E. Persistence layout

Статус: завершено.

- repository modules: 31;
- domain repositories: 30;
- infrastructure PostgreSQL adapters: 1;
- central repositories: 0;
- root repositories: 0;
- `velvet_bot/repositories` удалён;
- новые persistence modules допускаются только в domain либо reviewed infrastructure boundary.

### P3F. Статическая типизация

Статус: следующий кодовый срез.

Статический анализ включается постепенно для transport-neutral слоёв: core, application, domains, services и workers. Первый baseline ограничивается выбранным пакетом и запрещает новые typing errors только в его scope. Полное включение strict-mode одним изменением запрещено.""",
    )
    replace_once(
        path,
        "- `docs/legacy_handler_consumer_inventory.*` — измеримый baseline старых handler imports;",
        "- `docs/legacy_handler_consumer_inventory.*` — закрытый baseline старых handler imports;\n- `docs/repository_layout_inventory.*` — завершённая P3E-карта persistence;\n- `docs/architecture_layout_inventory.*` — физическая структура, root modules и runtime compatibility;",
    )


def update_project_memory() -> None:
    path = "docs/project_memory.md"
    replace_once(path, "Дата актуализации: 20 июля 2026 года.", "Дата актуализации: 21 июля 2026 года.")
    replace_section(
        path,
        "# Линия D. Стабильность P2",
        "# Линия E. Организация структуры P3",
        """# Линия D. Стабильность P2

Статус: завершена.

Актуальный generated inventory после owner diagnostics:

- broad exception boundaries: 76;
- approved boundaries: 76;
- unresolved boundaries: 0;
- callback handlers: 98;
- late/missing callbacks: 0;
- следующий срез отсутствует.

Широкие catches сохранены только как проверенные внешние границы с логированием/компенсацией. `asyncio.CancelledError` не поглощается.""",
    )
    replace_section(
        path,
        "# Линия E. Организация структуры P3",
        "# Открытые обязательства",
        """# Линия E. Организация структуры P3

Цель: довести физическую структуру пакетов до уже существующих логических границ без массовой переписи работающего бота.

## P3A. Синхронизация источников истины

Статус: завершено.

Status, memory, audit, changelog и generated inventories синхронизированы с фактическим `main`. Эксплуатационные проверки не смешиваются с кодовыми архитектурными долгами.

## P3B. Telegram Router bundles

Статус: завершено.

- root router подключает четыре крупные доменные bundles;
- root router не импортирует `velvet_bot.handlers.*`;
- 60 активных router imports зарегистрированы без дублей;
- порядок регистрации защищается AST-тестом;
- публикации остаются перед архивным catch-all.

## P3C. Физический перенос presentation

Статус: завершено.

Все активные Telegram controllers находятся в `velvet_bot/presentation/telegram/routers/<domain>/`. Legacy handler-файлов, implementations и aliases осталось 0.

## P3D. Compatibility retirement

Статус handler aliases: завершено.

Production legacy-consumer inventory закрыт на 0/0/0, а старый `velvet_bot.handlers` слой удалён. В explicit registry остаются 8 runtime compatibility-компонентов, которые классифицируются отдельно как schema/UI/import-order adapters либо удаляются после миграции consumers.

## P3E. Repository layout

Статус: завершено.

Repository inventory фиксирует 31 module: 30 domain repositories и 1 PostgreSQL infrastructure adapter. Central и root repositories отсутствуют, пакет `velvet_bot/repositories` удалён. Новый persistence-код создаётся только внутри domain либо reviewed infrastructure boundary.

## P3F. Статическая типизация

Статус: следующий кодовый срез.

Типизация включается постепенно для transport-neutral слоёв. Сначала один ограниченный core/application/domain scope, затем services/workers и только потом Telegram adapters. Массовое включение strict-mode на весь repository запрещено без baseline и поэтапного плана.""",
    )


def update_architecture_audit() -> None:
    path = "docs/ARCHITECTURE_AUDIT.md"
    replace_once(path, "Дата актуализации: 20 июля 2026 года.", "Дата актуализации: 21 июля 2026 года.")
    replace_once(
        path,
        "Физическая структура пакетов остаётся переходной: активные Telegram controllers уже перенесены в `velvet_bot/presentation/telegram/routers`, production imports больше не используют старые handler paths, но 35 aliases сохраняются для тестовой и внешней совместимости. Часть repositories и services всё ещё расположена в исторических корневых модулях, а runtime compatibility adapters удаляются отдельными проверяемыми срезами.",
        "Физическая структура пакетов остаётся переходной только по 110 историческим root modules и 8 explicit runtime compatibility-компонентам. Активные Telegram controllers перенесены в `velvet_bot/presentation/telegram/routers`, старые handler paths и aliases удалены полностью, а все repositories размещены в domain либо PostgreSQL infrastructure boundary.",
    )
    replace_section(
        path,
        "### P2 stability",
        "### Telegram contracts",
        """### P2 stability

P2 закрыта. Актуальный generated baseline:

- 76 broad exception boundaries;
- 76 approved;
- 0 unresolved;
- 98 callback handlers;
- 0 late/missing acknowledgments.""",
    )
    replace_section(
        path,
        "## Текущая структура",
        "## P3A: источники истины",
        """## Текущая структура

```text
velvet_bot/
  app/                         composition root и lifecycle
  application/                 transport-neutral owner/use cases
  core/                        config, access и общие contracts
  domains/                     30 канонических repository boundaries
  infrastructure/              PostgreSQL/Telegram/filesystem/Krita adapters
  presentation/telegram/       root Router, views, contracts и 4 bundles
  services/                    application/integration services
  workers/                     WorkerManager и worker boundaries
  *.py                         110 исторических root modules для классификации
```

Handler compatibility слой и central/root repositories уже удалены. Оставшаяся физическая работа касается классификации root modules и 8 explicit runtime compatibility-компонентов, а не восстановления старых путей.""",
    )
    replace_section(
        path,
        "## P3A: источники истины",
        "## Эксплуатационные ворота",
        """## P3A: источники истины

Статус: завершено. Status, memory, audit, changelog и inventories синхронизированы с `main`.

## P3B: Telegram Router composition

Статус: завершено. Четыре ordered bundles содержат 60 активных routers без дублей; root composition не импортирует legacy handlers.

## P3C: физический перенос presentation

Статус: завершено. Legacy handler-файлов, implementations и aliases осталось 0.

## P3D: compatibility retirement

Handler compatibility retirement завершён. Старые handler paths не имеют consumers и удалены. Остаются 8 explicit runtime compatibility-компонентов: 7 pre-import и 1 post-import. Каждый дальнейший компонент должен стать постоянным contract либо быть удалён вместе с regression-тестом.

## P3E: repository layout

Статус: завершено.

- repository modules: 31;
- domain: 30;
- infrastructure/postgres: 1;
- central: 0;
- root: 0;
- пакет `velvet_bot/repositories` отсутствует.

## P3F: статическая типизация

Следующий кодовый срез:

- выбрать один transport-neutral package;
- создать ограниченный mypy/pyright baseline;
- блокировать новые typing errors в выбранном scope;
- расширять scope только после зелёного CI;
- не включать strict-mode на весь repository одним PR.""",
    )


def update_changelog() -> None:
    path = ROOT / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    marker = "## [Unreleased]\n"
    entry = """## [Unreleased]

### P3A: current source-of-truth synchronization

- Status, project memory and architecture audit now reflect the current merged architecture.
- P2 generated baseline is 76 approved broad boundaries, 0 unresolved and 98 callback handlers with 0 late/missing acknowledgments.
- Legacy handler files, implementations and aliases are all 0; four Telegram bundles register 60 active routers without duplicates.
- P3E is complete with 30 domain repositories, 1 PostgreSQL infrastructure adapter, 0 central repositories and 0 root repositories.
- Architecture inventory now points to the first bounded P3F static-typing baseline.
- Owner-only `Velvet Diagnostic Bundle v1` exports redacted runtime, worker, incident and log snapshots to the owner private chat.
- Qwen error retry preserves the `media_ai_profiles.analysis` NOT NULL invariant by resetting it to an empty JSON object.
"""
    if marker not in text:
        raise RuntimeError("CHANGELOG Unreleased marker missing")
    path.write_text(text.replace(marker, entry, 1), encoding="utf-8")


def update_inventory_generator() -> None:
    replace_once(
        "scripts/inventory_architecture_layout.py",
        '''        "next_slice": {
            "phase": "P3E",
            "target": "repository and root-module layout normalization",
            "strategy": "inventory repository consumers, then migrate one domain per reviewed slice",
        },''',
        '''        "next_slice": {
            "phase": "P3F",
            "target": "bounded static typing baseline",
            "strategy": "type-check one transport-neutral package, gate new errors, then expand scope",
        },''',
    )


def validate() -> None:
    current_docs = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "docs/development_status.md",
            "docs/project_memory.md",
            "docs/ARCHITECTURE_AUDIT.md",
        )
    )
    for stale in (
        "остаются 35 aliases",
        "46 временных module aliases",
        "Статус: открыт.\n\nНужно постепенно свести исторические варианты",
    ):
        if stale in current_docs:
            raise RuntimeError(f"stale current status remains: {stale}")
    for required in (
        "broad exception boundaries: 76",
        "callback handlers: 98",
        "domain repositories: 30",
        "P3F",
    ):
        if required not in current_docs:
            raise RuntimeError(f"missing synchronized fact: {required}")


def main() -> None:
    update_development_status()
    update_project_memory()
    update_architecture_audit()
    update_changelog()
    update_inventory_generator()
    validate()


if __name__ == "__main__":
    main()
