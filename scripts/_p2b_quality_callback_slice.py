from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "velvet_bot"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected block not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    ROOT / "velvet_bot/handlers/quality_ai.py",
    '''    changed = await AIQualityRepository(database).retry(callback_data.item_id)
    if isinstance(callback.message, Message):
        await _show_list(
            callback.message,
            database,
            section=callback_data.section or "review",
            page_number=callback_data.page,
        )
    await callback.answer(
        "Изображение возвращено в очередь." if changed else "Проверка не найдена.",
        show_alert=True,
    )
''',
    '''    changed = await AIQualityRepository(database).retry(callback_data.item_id)
    await callback.answer(
        "Изображение возвращено в очередь." if changed else "Проверка не найдена.",
        show_alert=True,
    )
    if isinstance(callback.message, Message):
        await _show_list(
            callback.message,
            database,
            section=callback_data.section or "review",
            page_number=callback_data.page,
        )
''',
)

replace_once(
    ROOT / "velvet_bot/handlers/quality_center.py",
    '''    count = await reset_failed_scans(database)
    if isinstance(callback.message, Message):
        await _show_section(
            callback.message,
            database,
            section="scan_errors",
            page_number=0,
        )
    await callback.answer(f"Возвращено в очередь: {count}.", show_alert=True)
''',
    '''    count = await reset_failed_scans(database)
    await callback.answer(f"Возвращено в очередь: {count}.", show_alert=True)
    if isinstance(callback.message, Message):
        await _show_section(
            callback.message,
            database,
            section="scan_errors",
            page_number=0,
        )
''',
)

replace_once(
    ROOT / "velvet_bot/handlers/quality_center.py",
    '''    count = await reset_broken_file_checks(database)
    if isinstance(callback.message, Message):
        await _show_section(
            callback.message,
            database,
            section="broken_files",
            page_number=0,
        )
    await callback.answer(f"На повторную проверку: {count}.", show_alert=True)
''',
    '''    count = await reset_broken_file_checks(database)
    await callback.answer(f"На повторную проверку: {count}.", show_alert=True)
    if isinstance(callback.message, Message):
        await _show_section(
            callback.message,
            database,
            section="broken_files",
            page_number=0,
        )
''',
)

replace_once(
    ROOT / "velvet_bot/handlers/quality_operations.py",
    '''    count = await QualityOperationsRepository(database).enqueue_recent(limit=24)
    if isinstance(callback.message, Message):
        await _show_menu(callback.message, database, worker_manager)
    await callback.answer(f"Поставлено или возвращено в очередь: {count}.", show_alert=True)
''',
    '''    count = await QualityOperationsRepository(database).enqueue_recent(limit=24)
    await callback.answer(f"Поставлено или возвращено в очередь: {count}.", show_alert=True)
    if isinstance(callback.message, Message):
        await _show_menu(callback.message, database, worker_manager)
''',
)

replace_once(
    ROOT / "velvet_bot/handlers/quality_operations.py",
    '''    count = await QualityOperationsRepository(database).retry_errors()
    if isinstance(callback.message, Message):
        await _show_menu(callback.message, database, worker_manager)
    await callback.answer(f"Возвращено в очередь: {count}.", show_alert=True)
''',
    '''    count = await QualityOperationsRepository(database).retry_errors()
    await callback.answer(f"Возвращено в очередь: {count}.", show_alert=True)
    if isinstance(callback.message, Message):
        await _show_menu(callback.message, database, worker_manager)
''',
)


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Call):
        return dotted(node.func)
    return ""


def broad_handler(node: ast.ExceptHandler) -> bool:
    value = node.type
    if isinstance(value, ast.Name):
        return value.id == "Exception"
    if isinstance(value, ast.Tuple):
        return any(
            isinstance(item, ast.Name) and item.id == "Exception"
            for item in value.elts
        )
    return False


def callback_decorated(node: ast.AsyncFunctionDef) -> bool:
    return any("callback_query" in dotted(item) for item in node.decorator_list)


def acknowledgement(node: ast.Await) -> bool:
    name = dotted(node.value)
    leaf = name.rsplit(".", 1)[-1].casefold()
    return name.endswith("callback.answer") or (
        "callback" in leaf and ("answer" in leaf or "acknowledge" in leaf)
    )


def passes_callback(node: ast.Await) -> bool:
    value = node.value
    if not isinstance(value, ast.Call):
        return False
    arguments = [*value.args, *(item.value for item in value.keywords)]
    return any(
        isinstance(item, ast.Name) and item.id == "callback" for item in arguments
    )


broad: list[dict[str, object]] = []
callbacks: list[dict[str, object]] = []
for path in sorted(PACKAGE.rglob("*.py")):
    relative = path.relative_to(ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
    parents: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            parents.append(node.name)
            self.generic_visit(node)
            parents.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            function = ".".join([*parents, node.name])
            if callback_decorated(node):
                awaits = sorted(
                    (
                        item
                        for item in ast.walk(node)
                        if isinstance(item, ast.Await)
                    ),
                    key=lambda item: (item.lineno, item.col_offset),
                )
                ack = next((item for item in awaits if acknowledgement(item)), None)
                pre = [
                    item
                    for item in awaits
                    if ack is None or item.lineno < ack.lineno
                ]
                delegated = (
                    ack is None
                    and len(awaits) == 1
                    and passes_callback(awaits[0])
                )
                if delegated:
                    risk = "delegated"
                elif ack is None:
                    risk = "missing_ack"
                elif not pre:
                    risk = "early_ack"
                elif len(pre) == 1:
                    risk = "guarded_ack"
                else:
                    risk = "late_ack"
                callbacks.append(
                    {
                        "path": relative,
                        "function": function,
                        "line": node.lineno,
                        "ack_line": ack.lineno if ack else None,
                        "pre_ack_awaits": len(pre),
                        "total_awaits": len(awaits),
                        "risk": risk,
                    }
                )
            parents.append(node.name)
            self.generic_visit(node)
            parents.pop()

        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
            if broad_handler(node):
                broad.append(
                    {
                        "path": relative,
                        "function": ".".join(parents) or "<module>",
                        "line": node.lineno,
                        "handler_module": "/handlers/" in f"/{relative}",
                    }
                )
            self.generic_visit(node)

    Visitor().visit(tree)

priority = {
    "missing_ack": 0,
    "late_ack": 1,
    "guarded_ack": 2,
    "delegated": 3,
    "early_ack": 4,
}
callbacks.sort(
    key=lambda item: (
        priority[str(item["risk"])],
        -int(item["pre_ack_awaits"]),
        str(item["path"]),
        int(item["line"]),
    )
)
broad.sort(key=lambda item: (str(item["path"]), int(item["line"])))
risky = [
    item for item in callbacks if item["risk"] in {"missing_ack", "late_ack"}
]
guarded = [item for item in callbacks if item["risk"] == "guarded_ack"]
delegated = [item for item in callbacks if item["risk"] == "delegated"]

inventory = {
    "schema_version": 4,
    "generated_from_commit": "p2b-quality-callback-ack",
    "broad_exception_total": len(broad),
    "broad_exception_files": len({str(item["path"]) for item in broad}),
    "callback_total": len(callbacks),
    "risky_callback_total": len(risky),
    "risky_callback_files": len({str(item["path"]) for item in risky}),
    "guarded_callback_total": len(guarded),
    "delegated_callback_total": len(delegated),
    "next_slice": {
        "target": "velvet_bot/domains/publication/service.py",
        "kind": "broad_exception_triage",
    },
    "broad_exceptions": broad,
    "callbacks": callbacks,
}
(ROOT / "docs/p2_stability_inventory.json").write_text(
    json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

broad_by_file = Counter(str(item["path"]) for item in broad)
lines = [
    "# P2 stability inventory",
    "",
    "AST-инвентаризация широких исключений и callback acknowledgment.",
    "",
    "## Сводка",
    "",
    f"- широких `except Exception`: **{len(broad)}** в **{len(broad_by_file)}** файлах;",
    f"- callback handlers: **{len(callbacks)}**;",
    f"- missing/late acknowledgment: **{len(risky)}**;",
    f"- guarded acknowledgment после одной mutation/query: **{len(guarded)}**;",
    f"- delegated wrappers: **{len(delegated)}**.",
    "",
    "## Risky callbacks",
    "",
]
if risky:
    for item in risky:
        lines.append(
            f"- `{item['path']}:{item['line']}` `{item['function']}`: "
            f"{item['risk']}, awaits до ack: {item['pre_ack_awaits']}."
        )
else:
    lines.append("- Нет. Callback late/missing baseline закрыт.")
lines.extend(["", "## Guarded acknowledgment", ""])
for item in guarded:
    lines.append(f"- `{item['path']}:{item['line']}` `{item['function']}`.")
lines.extend(["", "## Delegated wrappers", ""])
for item in delegated:
    lines.append(f"- `{item['path']}:{item['line']}` `{item['function']}`.")
lines.extend(["", "## Широкие исключения по файлам", ""])
for path, count in broad_by_file.most_common():
    lines.append(f"- `{path}`: {count}.")
lines.extend(
    [
        "",
        "## Следующий срез",
        "",
        "- `velvet_bot/domains/publication/service.py`: классифицировать broad exceptions и сузить бизнес-ошибки без потери incident reporting.",
        "",
        "## Правило обновления",
        "",
        "Inventory проверяется AST-тестом. Тяжёлый reload должен выполняться после callback acknowledgment.",
        "",
    ]
)
(ROOT / "docs/p2_stability_inventory.md").write_text(
    "\n".join(lines), encoding="utf-8"
)

status_path = ROOT / "docs/development_status.md"
status = status_path.read_text(encoding="utf-8")
status = status.replace(
    "2. Исправлять risky callbacks отдельными поведенческими срезами.",
    "2. P2B: late/missing callback baseline закрыт 0; quality retry/reset/enqueue подтверждаются до reload UI.",
)
status_path.write_text(status, encoding="utf-8")

memory_path = ROOT / "docs/project_memory.md"
memory = memory_path.read_text(encoding="utf-8")
memory = memory.replace(
    "2. Исправлять risky callbacks отдельными поведенческими срезами.",
    "2. P2B: late/missing callback baseline закрыт 0; quality callbacks подтверждаются до reload UI.",
)
memory_path.write_text(memory, encoding="utf-8")

changelog_path = ROOT / "CHANGELOG.md"
changelog = changelog_path.read_text(encoding="utf-8")
marker = "## [Unreleased]\n"
entry = (
    "\n### P2B: quality callback acknowledgment\n\n"
    "- Retry/reset/enqueue callbacks отвечают после mutation result и до тяжёлого UI reload.\n"
    "- Late/missing callback baseline уменьшен с 5 до 0.\n"
)
if entry.strip() not in changelog:
    changelog = changelog.replace(marker, marker + entry, 1)
changelog_path.write_text(changelog, encoding="utf-8")

(ROOT / "tests/test_p2b_quality_callback_ack.py").write_text(
    '''from __future__ import annotations

import inspect
import unittest

import velvet_bot.handlers.quality_ai as quality_ai
import velvet_bot.handlers.quality_center as quality_center
import velvet_bot.handlers.quality_operations as quality_operations


class QualityCallbackAcknowledgmentTests(unittest.TestCase):
    def assert_ack_between(self, function, mutation: str, reload_call: str) -> None:
        source = inspect.getsource(function)
        self.assertLess(source.index(mutation), source.index("await callback.answer("))
        self.assertLess(source.index("await callback.answer("), source.index(reload_call))

    def test_retry_ack_precedes_list_reload(self) -> None:
        self.assert_ack_between(
            quality_ai.handle_quality_ai_retry,
            "await AIQualityRepository(database).retry(",
            "await _show_list(",
        )

    def test_reset_callbacks_ack_before_section_reload(self) -> None:
        self.assert_ack_between(
            quality_center.handle_retry_scans,
            "await reset_failed_scans(",
            "await _show_section(",
        )
        self.assert_ack_between(
            quality_center.handle_retry_broken,
            "await reset_broken_file_checks(",
            "await _show_section(",
        )

    def test_queue_callbacks_ack_before_menu_reload(self) -> None:
        self.assert_ack_between(
            quality_operations.handle_quality_recent,
            "await QualityOperationsRepository(database).enqueue_recent(",
            "await _show_menu(",
        )
        self.assert_ack_between(
            quality_operations.handle_quality_retry_errors,
            "await QualityOperationsRepository(database).retry_errors(",
            "await _show_menu(",
        )


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)

(ROOT / "docs/worklog/2026-07-18-p2b-quality-callback-ack.md").write_text(
    '''# Сессия: P2B — quality callback acknowledgment

- Дата: 2026-07-18
- ID: `2026-07-18-p2b-quality-callback-ack`
- Линия/фаза: основное развитие Velvet Archive, P2B
- Статус: завершено
- Ветка: `agent/p2b-quality-callback-ack`
- Базовый commit: `324f18a52a4be2f12ce3303ea3f619bd8861d84e`

## Перед началом

### Цель

Закрыть пять оставшихся late callbacks, сохранив mutation-result alert и перенеся тяжёлый UI reload после acknowledgment.

### Исходный контекст

P2A создала baseline: 5 late/missing callbacks в 3 файлах. Все пять выполняли одну mutation/query, затем reload UI и только после этого отвечали Telegram.

### Планируемый объём

1. Переставить acknowledgment в quality AI retry.
2. Переставить acknowledgment в два quality center reset callback.
3. Переставить acknowledgment в два quality operations queue callback.
4. Пересчитать inventory.
5. Добавить source-order regression tests.

### Критерии готовности

- mutation result и alert text сохранены;
- acknowledgment выполняется до reload UI;
- risky callback baseline равен 0;
- полный PR CI зелёный.

### Риски и ограничения

Mutation/query остаётся до acknowledgment, чтобы сохранить точный count/result. Она классифицируется как guarded; тяжёлая перерисовка переносится после ответа.

## После завершения

### Фактически сделано

- пять callbacks переведены из late в guarded;
- callback late/missing baseline уменьшен с 5 до 0;
- общий callback count и payload не изменены;
- добавлены source-order tests;
- inventory, status, memory и changelog синхронизированы.

### Миграции и совместимость

Миграции, callback payload, тексты alert и repository operations не изменялись.

### Проверки

Требуются unit tests, Docker build и project notes contract на финальном head.

### PR и commit

PR создаётся после выполнения подготовительного runner; номер фиксируется финальным connector-коммитом.

### Незавершённое

Остаётся broad-exception baseline: 70 в 43 файлах.

### Следующий шаг

Классифицировать и сузить broad exceptions в `velvet_bot/domains/publication/service.py`.
''',
    encoding="utf-8",
)
