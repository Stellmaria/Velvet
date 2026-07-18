from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "p2-approved-boundary: compensate-claimed-media-scan"

service_path = ROOT / "velvet_bot/domains/media_quality/service.py"
service = service_path.read_text(encoding="utf-8")
old = "        except Exception as error:\n            logger.exception(\"Visual fingerprint failed media_id=%s\", target.media_id)"
new = (
    f"        except Exception as error:  # {MARKER}\n"
    "            logger.exception(\"Visual fingerprint failed media_id=%s\", target.media_id)"
)
if old not in service:
    raise RuntimeError("Media quality broad boundary was not found")
service_path.write_text(service.replace(old, new, 1), encoding="utf-8")

inventory_path = ROOT / "docs/p2_stability_inventory.json"
data = json.loads(inventory_path.read_text(encoding="utf-8"))
matched = 0
for item in data["broad_exceptions"]:
    if (
        item["path"] == "velvet_bot/domains/media_quality/service.py"
        and item["function"] == "scan_target"
    ):
        item["classification"] = "approved_boundary"
        item["reason"] = "compensate-claimed-media-scan"
        matched += 1
if matched != 1:
    raise RuntimeError(f"Expected one media-quality inventory item, got {matched}")

approved = [
    item
    for item in data["broad_exceptions"]
    if item["classification"] == "approved_boundary"
]
unresolved = [
    item
    for item in data["broad_exceptions"]
    if item["classification"] == "unresolved"
]
data["schema_version"] = 6
data["generated_from_commit"] = "p2d-media-quality-boundary"
data["broad_exception_approved"] = len(approved)
data["broad_exception_unresolved"] = len(unresolved)
data["broad_exception_unresolved_files"] = len(
    {str(item["path"]) for item in unresolved}
)
data["next_slice"] = {
    "target": "velvet_bot/ai_quality.py",
    "kind": "broad_exception_triage",
}
inventory_path.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

unresolved_by_file = Counter(str(item["path"]) for item in unresolved)
risky = [
    item
    for item in data["callbacks"]
    if item["risk"] in {"missing_ack", "late_ack"}
]
lines = [
    "# P2 stability inventory",
    "",
    "AST-инвентаризация широких исключений и callback acknowledgment.",
    "",
    "## Сводка",
    "",
    f"- broad exceptions raw: **{data['broad_exception_total']}** в **{data['broad_exception_files']}** файлах;",
    f"- approved orchestration boundaries: **{len(approved)}**;",
    f"- unresolved broad exceptions: **{len(unresolved)}** в **{len(unresolved_by_file)}** файлах;",
    f"- callback handlers: **{data['callback_total']}**;",
    f"- missing/late acknowledgment: **{data['risky_callback_total']}**;",
    f"- guarded acknowledgment: **{data['guarded_callback_total']}**;",
    f"- delegated wrappers: **{data['delegated_callback_total']}**.",
    "",
    "## Approved broad boundaries",
    "",
]
for item in approved:
    lines.append(
        f"- `{item['path']}:{item['line']}` `{item['function']}`: {item['reason']}."
    )
lines.extend(["", "## Unresolved broad exceptions by file", ""])
for path, count in unresolved_by_file.most_common():
    lines.append(f"- `{path}`: {count}.")
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
        "- `velvet_bot/ai_quality.py`: broad-exception triage worker item boundary.",
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

(ROOT / "tests/test_p2d_media_quality_boundary.py").write_text(
    '''from __future__ import annotations

import asyncio
import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.media_quality.models import MediaScanTarget
from velvet_bot.domains.media_quality.service import MediaQualityService


class MediaQualityBroadBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_scan_compensation_boundary_is_explicit(self) -> None:
        source = inspect.getsource(MediaQualityService.scan_target)
        self.assertIn(
            "p2-approved-boundary: compensate-claimed-media-scan",
            source,
        )

    async def test_unexpected_scan_failure_is_recorded_for_claimed_target(self) -> None:
        error = RuntimeError("download failed")
        bot = SimpleNamespace(download=AsyncMock(side_effect=error))
        repository = SimpleNamespace(mark_scan_error=AsyncMock())
        service = MediaQualityService(bot=bot, repository=repository)
        target = MediaScanTarget(
            media_id=17,
            telegram_file_id="file-id",
            display_name="image.jpg",
        )

        await service.scan_target(target)

        repository.mark_scan_error.assert_awaited_once_with(
            media_id=17,
            error=error,
            broken_file=False,
        )

    async def test_scan_cancellation_is_not_compensated_or_suppressed(self) -> None:
        bot = SimpleNamespace(
            download=AsyncMock(side_effect=asyncio.CancelledError())
        )
        repository = SimpleNamespace(mark_scan_error=AsyncMock())
        service = MediaQualityService(bot=bot, repository=repository)
        target = MediaScanTarget(
            media_id=18,
            telegram_file_id="file-id",
            display_name="image.jpg",
        )

        with self.assertRaises(asyncio.CancelledError):
            await service.scan_target(target)

        repository.mark_scan_error.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)

status_path = ROOT / "docs/development_status.md"
status = status_path.read_text(encoding="utf-8")
status = status.replace(
    "3. P2C: publication broad boundaries классифицированы; unresolved broad baseline 70 → 68.",
    "3. P2D: media-quality claimed-scan compensation boundary классифицирован; unresolved broad baseline 68 → 67.",
)
status_path.write_text(status, encoding="utf-8")

memory_path = ROOT / "docs/project_memory.md"
memory = memory_path.read_text(encoding="utf-8")
memory = memory.replace(
    "3. P2C: publication compensation/isolation boundaries классифицированы; unresolved broad baseline 70 → 68.",
    "3. P2D: media-quality claimed-scan compensation boundary классифицирован; unresolved broad baseline 68 → 67.",
)
memory_path.write_text(memory, encoding="utf-8")

changelog_path = ROOT / "CHANGELOG.md"
changelog = changelog_path.read_text(encoding="utf-8")
marker = "## [Unreleased]\n"
entry = (
    "\n### P2D: media-quality scan boundary\n\n"
    "- Claimed media scan broad catch отмечен как approved compensation boundary.\n"
    "- Добавлены тесты записи scan error и cancellation propagation.\n"
    "- Unresolved broad-exception baseline уменьшен с 68 до 67.\n"
)
if entry.strip() not in changelog:
    changelog = changelog.replace(marker, marker + entry, 1)
changelog_path.write_text(changelog, encoding="utf-8")

(ROOT / "docs/worklog/2026-07-18-p2d-media-quality-boundary.md").write_text(
    '''# Сессия: P2D — media-quality scan boundary

- Дата: 2026-07-18
- ID: `2026-07-18-p2d-media-quality-boundary`
- Линия/фаза: основное развитие Velvet Archive, P2D
- Статус: завершено
- Ветка: `agent/p2d-media-quality-boundary`
- Базовый commit: `c992a40c473549cc9236cb4d0aca9697a2880f15`

## Перед началом

### Цель

Классифицировать broad catch `MediaQualityService.scan_target()` как claimed-item compensation boundary и закрепить запись ошибки и cancellation propagation тестами.

### Исходный контекст

P2C разделила raw, approved и unresolved broad debt. Baseline: 70 raw, 2 approved, 68 unresolved в 42 файлах.

### Планируемый объём

1. Добавить inline approved marker.
2. Проверить unexpected failure → `mark_scan_error`.
3. Проверить, что cancellation не подавляется.
4. Обновить inventory и проектные документы.

### Критерии готовности

- claimed scan не остаётся без статуса при неизвестной ошибке;
- `broken_file=False` сохраняется для non-Telegram failure;
- cancellation выходит наружу;
- unresolved baseline уменьшается 68 → 67;
- полный PR CI зелёный.

### Риски и ограничения

Raw catch сохраняется намеренно: target уже claimed, поэтому неизвестный fingerprint/persistence failure должен завершиться scan-error state. Telegram-specific branches не меняются.

## После завершения

### Фактически сделано

- scan broad catch отмечен approved boundary;
- unexpected failure записывает исходный error с `broken_file=False`;
- cancellation не вызывает compensation и не подавляется;
- approved baseline увеличен 2 → 3;
- unresolved baseline уменьшен 68 → 67;
- inventory, changelog, status и memory синхронизированы.

### Миграции и совместимость

Миграции, Telegram error handling и repository API не изменялись.

### Проверки

Требуются unit tests, Docker build и project notes contract на финальном head.

### PR и commit

PR создаётся после runner; номер фиксируется финальным connector-коммитом.

### Незавершённое

Остаётся 67 unresolved broad exceptions.

### Следующий шаг

Broad-exception triage в `velvet_bot/ai_quality.py`.
''',
    encoding="utf-8",
)
