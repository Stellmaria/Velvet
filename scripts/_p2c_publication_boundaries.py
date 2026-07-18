from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "velvet_bot"
MARKER = "p2-approved-boundary:"

service_path = ROOT / "velvet_bot/domains/publication/service.py"
service = service_path.read_text(encoding="utf-8")
service = service.replace(
    "        except Exception as error:\n            logger.exception(\"Publication failed draft_id=%s\", draft_id)",
    "        except Exception as error:  # p2-approved-boundary: compensate-claimed-publication\n            logger.exception(\"Publication failed draft_id=%s\", draft_id)",
    1,
)
service = service.replace(
    "            except Exception:\n                logger.exception(\"Scheduled publication failed draft_id=%s\", draft_id)",
    "            except Exception:  # p2-approved-boundary: isolate-scheduled-draft\n                logger.exception(\"Scheduled publication failed draft_id=%s\", draft_id)",
    1,
)
if service.count(MARKER) != 2:
    raise RuntimeError("Publication broad-boundary markers were not applied exactly twice")
service_path.write_text(service, encoding="utf-8")


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
    source = path.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    tree = ast.parse(source, filename=relative)
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
                line = source_lines[node.lineno - 1]
                approved = MARKER in line
                reason = line.split(MARKER, 1)[1].strip() if approved else None
                broad.append(
                    {
                        "path": relative,
                        "function": ".".join(parents) or "<module>",
                        "line": node.lineno,
                        "handler_module": "/handlers/" in f"/{relative}",
                        "classification": (
                            "approved_boundary" if approved else "unresolved"
                        ),
                        "reason": reason,
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
approved = [item for item in broad if item["classification"] == "approved_boundary"]
unresolved = [item for item in broad if item["classification"] == "unresolved"]

inventory = {
    "schema_version": 5,
    "generated_from_commit": "p2c-publication-boundaries",
    "broad_exception_total": len(broad),
    "broad_exception_files": len({str(item["path"]) for item in broad}),
    "broad_exception_approved": len(approved),
    "broad_exception_unresolved": len(unresolved),
    "broad_exception_unresolved_files": len(
        {str(item["path"]) for item in unresolved}
    ),
    "callback_total": len(callbacks),
    "risky_callback_total": len(risky),
    "risky_callback_files": len({str(item["path"]) for item in risky}),
    "guarded_callback_total": len(guarded),
    "delegated_callback_total": len(delegated),
    "next_slice": {
        "target": "velvet_bot/domains/media_quality/service.py",
        "kind": "broad_exception_triage",
    },
    "broad_exceptions": broad,
    "callbacks": callbacks,
}
(ROOT / "docs/p2_stability_inventory.json").write_text(
    json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

unresolved_by_file = Counter(str(item["path"]) for item in unresolved)
lines = [
    "# P2 stability inventory",
    "",
    "AST-инвентаризация широких исключений и callback acknowledgment.",
    "",
    "## Сводка",
    "",
    f"- broad exceptions raw: **{len(broad)}** в **{len({str(item['path']) for item in broad})}** файлах;",
    f"- approved orchestration boundaries: **{len(approved)}**;",
    f"- unresolved broad exceptions: **{len(unresolved)}** в **{len(unresolved_by_file)}** файлах;",
    f"- callback handlers: **{len(callbacks)}**;",
    f"- missing/late acknowledgment: **{len(risky)}**;",
    f"- guarded acknowledgment: **{len(guarded)}**;",
    f"- delegated wrappers: **{len(delegated)}**.",
    "",
    "## Approved broad boundaries",
    "",
]
for item in approved:
    lines.append(
        f"- `{item['path']}:{item['line']}` `{item['function']}`: {item['reason']}."
    )
if not approved:
    lines.append("- Нет.")
lines.extend(["", "## Unresolved broad exceptions by file", ""])
for path, count in unresolved_by_file.most_common():
    lines.append(f"- `{path}`: {count}.")
if not unresolved_by_file:
    lines.append("- Нет.")
lines.extend(["", "## Risky callbacks", ""])
if risky:
    for item in risky:
        lines.append(
            f"- `{item['path']}:{item['line']}` `{item['function']}`: {item['risk']}."
        )
else:
    lines.append("- Нет. Callback late/missing baseline закрыт.")
lines.extend(
    [
        "",
        "## Следующий срез",
        "",
        "- `velvet_bot/domains/media_quality/service.py`: broad-exception triage.",
        "",
        "## Правило обновления",
        "",
        "Approved boundary требует inline-маркер и отдельный поведенческий тест. Raw count не уменьшается от классификации; unresolved count отражает оставшийся долг.",
        "",
    ]
)
(ROOT / "docs/p2_stability_inventory.md").write_text(
    "\n".join(lines), encoding="utf-8"
)

inventory_test = ROOT / "tests/test_p2_stability_inventory.py"
test_source = inventory_test.read_text(encoding="utf-8")
test_source = test_source.replace(
    "def _actual() -> tuple[int, int, int, int, int, int, int]:",
    "def _actual() -> tuple[int, int, int, int, int, int, int, int, int, int]:",
    1,
)
test_source = test_source.replace(
    "    broad: list[tuple[str, int]] = []",
    "    broad: list[tuple[str, int, bool]] = []",
    1,
)
test_source = test_source.replace(
    "                broad.append((path.as_posix(), node.lineno))",
    "                line = path.read_text(encoding=\"utf-8\").splitlines()[node.lineno - 1]\n                broad.append((path.as_posix(), node.lineno, \"p2-approved-boundary:\" in line))",
    1,
)
test_source = test_source.replace(
    "    return (\n        len(broad),\n        len({path for path, _ in broad}),",
    "    approved = [item for item in broad if item[2]]\n    unresolved = [item for item in broad if not item[2]]\n    return (\n        len(broad),\n        len({path for path, _, _ in broad}),\n        len(approved),\n        len(unresolved),\n        len({path for path, _, _ in unresolved}),",
    1,
)
test_source = test_source.replace(
    "                data[\"broad_exception_files\"],\n                data[\"callback_total\"],",
    "                data[\"broad_exception_files\"],\n                data[\"broad_exception_approved\"],\n                data[\"broad_exception_unresolved\"],\n                data[\"broad_exception_unresolved_files\"],\n                data[\"callback_total\"],",
    1,
)
inventory_test.write_text(test_source, encoding="utf-8")

(ROOT / "tests/test_p2c_publication_boundaries.py").write_text(
    '''from __future__ import annotations

import asyncio
import inspect
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.publication.models import PublicationDraft
from velvet_bot.domains.publication.service import PublicationService


def _draft(draft_id: int = 1) -> PublicationDraft:
    now = datetime.now(timezone.utc)
    return PublicationDraft(
        id=draft_id,
        owner_id=7,
        target_chat_id=-1001,
        source_chat_id=None,
        source_message_id=None,
        source_media_group_id=None,
        text_content="test",
        status="checked",
        post_type="prompt",
        has_spoiler=False,
        content_hash="hash",
        validation_status="valid",
        validation_error_count=0,
        validation_warning_count=0,
        validation_report=(),
        scheduled_at=None,
        published_at=None,
        published_message_ids=(),
        attempt_count=0,
        last_error=None,
        created_at=now,
        updated_at=now,
        items=(),
    )


class PublicationBroadBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_boundaries_are_explicitly_marked(self) -> None:
        source = inspect.getsource(PublicationService)
        self.assertEqual(2, source.count("p2-approved-boundary:"))
        self.assertIn("compensate-claimed-publication", source)
        self.assertIn("isolate-scheduled-draft", source)

    async def test_delivery_failure_marks_claimed_draft_error_and_reraises(self) -> None:
        draft = _draft()
        repository = SimpleNamespace(
            get_draft=AsyncMock(side_effect=[draft, draft]),
            claim_for_publishing=AsyncMock(return_value=True),
            mark_published=AsyncMock(),
            mark_error=AsyncMock(),
        )
        delivery = SimpleNamespace(send=AsyncMock(side_effect=RuntimeError("send failed")))
        service = PublicationService(
            repository=repository,
            delivery=delivery,
            validator=AsyncMock(),
        )

        with self.assertRaisesRegex(RuntimeError, "send failed"):
            await service.publish(1)

        repository.mark_error.assert_awaited_once()
        repository.mark_published.assert_not_awaited()

    async def test_mark_published_failure_is_compensated_and_reraised(self) -> None:
        draft = _draft()
        repository = SimpleNamespace(
            get_draft=AsyncMock(side_effect=[draft, draft]),
            claim_for_publishing=AsyncMock(return_value=True),
            mark_published=AsyncMock(side_effect=RuntimeError("commit failed")),
            mark_error=AsyncMock(),
        )
        delivery = SimpleNamespace(send=AsyncMock(return_value=[11]))
        service = PublicationService(
            repository=repository,
            delivery=delivery,
            validator=AsyncMock(),
        )

        with self.assertRaisesRegex(RuntimeError, "commit failed"):
            await service.publish(1)

        repository.mark_error.assert_awaited_once()

    async def test_scheduled_failure_is_isolated_and_later_draft_continues(self) -> None:
        repository = SimpleNamespace(
            list_due_draft_ids=AsyncMock(return_value=[1, 2]),
        )
        service = PublicationService(
            repository=repository,
            delivery=SimpleNamespace(),
            validator=AsyncMock(),
        )
        service.publish = AsyncMock(side_effect=[RuntimeError("first"), _draft(2)])

        published = await service.process_due_once(limit=5)

        self.assertEqual(1, published)
        self.assertEqual(2, service.publish.await_count)

    async def test_scheduled_cancellation_is_not_isolated(self) -> None:
        repository = SimpleNamespace(
            list_due_draft_ids=AsyncMock(return_value=[1]),
        )
        service = PublicationService(
            repository=repository,
            delivery=SimpleNamespace(),
            validator=AsyncMock(),
        )
        service.publish = AsyncMock(side_effect=asyncio.CancelledError())

        with self.assertRaises(asyncio.CancelledError):
            await service.process_due_once()


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)

status_path = ROOT / "docs/development_status.md"
status = status_path.read_text(encoding="utf-8")
status = status.replace(
    "3. Сокращать широкие исключения по доменам без потери incident reporting.",
    "3. P2C: publication broad boundaries классифицированы; unresolved broad baseline 70 → 68.",
)
status_path.write_text(status, encoding="utf-8")

memory_path = ROOT / "docs/project_memory.md"
memory = memory_path.read_text(encoding="utf-8")
memory = memory.replace(
    "3. Сокращать широкие `except Exception` в бизнес-логике без потери диагностики.",
    "3. P2C: publication compensation/isolation boundaries классифицированы; unresolved broad baseline 70 → 68.",
)
memory_path.write_text(memory, encoding="utf-8")

changelog_path = ROOT / "CHANGELOG.md"
changelog = changelog_path.read_text(encoding="utf-8")
marker = "## [Unreleased]\n"
entry = (
    "\n### P2C: publication broad boundaries\n\n"
    "- Publication compensation и scheduled-item isolation отмечены как approved orchestration boundaries.\n"
    "- Добавлены тесты mark-error compensation, queue isolation и cancellation propagation.\n"
    "- Unresolved broad-exception baseline уменьшен с 70 до 68.\n"
)
if entry.strip() not in changelog:
    changelog = changelog.replace(marker, marker + entry, 1)
changelog_path.write_text(changelog, encoding="utf-8")

(ROOT / "docs/worklog/2026-07-18-p2c-publication-boundaries.md").write_text(
    '''# Сессия: P2C — publication broad boundaries

- Дата: 2026-07-18
- ID: `2026-07-18-p2c-publication-boundaries`
- Линия/фаза: основное развитие Velvet Archive, P2C
- Статус: завершено
- Ветка: `agent/p2c-publication-boundaries`
- Базовый commit: `f19ad75b304d94d5b971e7869a34bcd1ecbdf5e2`

## Перед началом

### Цель

Классифицировать два broad exceptions publication service как явные orchestration boundaries и закрепить их компенсационные контракты тестами.

### Исходный контекст

P2B закрыла callback late/missing baseline. Broad inventory содержала 70 необработанных записей в 43 файлах, включая два `except Exception` publication service.

### Планируемый объём

1. Отметить claim compensation boundary в `publish()`.
2. Отметить per-item isolation boundary в `process_due_once()`.
3. Разделить raw, approved и unresolved broad counts.
4. Добавить tests compensation, isolation и cancellation.
5. Синхронизировать inventory и проектные документы.

### Критерии готовности

- raw broad count остаётся честным;
- approved boundaries имеют inline marker и tests;
- unresolved broad baseline уменьшается 70 → 68;
- cancellation не подавляется;
- полный PR CI зелёный.

### Риски и ограничения

Broad catch внутри claim lifecycle сохраняется намеренно: неизвестная ошибка после claim должна перевести draft в error. Scheduled loop сохраняет изоляцию отдельных draft. Классификация не считается удалением raw catch.

## После завершения

### Фактически сделано

- два publication catches отмечены approved boundary markers;
- inventory schema разделяет raw, approved и unresolved debt;
- raw baseline остаётся 70/43;
- approved baseline равен 2;
- unresolved baseline уменьшен до 68;
- добавлены tests delivery failure compensation, mark-published compensation, scheduled isolation и cancellation propagation.

### Миграции и совместимость

Миграции, API service, repository и delivery protocols не изменялись.

### Проверки

Требуются unit tests, Docker build и project notes contract на финальном head.

### PR и commit

PR создаётся после runner; номер фиксируется финальным connector-коммитом.

### Незавершённое

Остаётся 68 unresolved broad exceptions.

### Следующий шаг

Broad-exception triage в `velvet_bot/domains/media_quality/service.py`.
''',
    encoding="utf-8",
)
