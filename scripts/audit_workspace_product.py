from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "audits" / "workspace_product_gap_audit.json"
REPORT = ROOT / "docs" / "audits" / "workspace_product_gap_audit.md"
ALLOWED_STATUSES = {"verified", "verified_with_follow_up", "live_follow_up"}


def _load() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _issues(values: list[int]) -> str:
    return ", ".join(f"#{value}" for value in values) if values else "—"


def render(data: dict[str, Any]) -> str:
    requirements = data["requirements"]
    verified = sum(item["status"] == "verified" for item in requirements)
    follow_up = sum(item["status"] != "verified" for item in requirements)
    lines = [
        "# Gap-аудит канонического ТЗ workspace",
        "",
        f"- Источник: `{data['source']}`",
        f"- Дата аудита: `{data['audited_at']}`",
        f"- Родительская issue: `#{data['issue']}`",
        f"- Полностью подтверждено: **{verified}** строк",
        f"- Подтверждено с follow-up или live-приёмкой: **{follow_up}** строк",
        "",
        "## Матрица",
        "",
        "| ID | Раздел | Требование | Статус | Реализация | Тесты | Follow-up |",
        "|---|---:|---|---|---|---|---|",
    ]
    for item in requirements:
        section = str(item["section"]) if item["section"] is not None else "ops"
        implementation = "<br>".join(
            f"`{path}`" for path in item["implementation"]
        )
        tests = "<br>".join(f"`{path}`" for path in item["tests"]) or "live"
        lines.append(
            "| {id} | {section} | {title} | `{status}` | {implementation} | "
            "{tests} | {follow_up} |".format(
                id=item["id"],
                section=section,
                title=item["title"],
                status=item["status"],
                implementation=implementation,
                tests=tests,
                follow_up=_issues(item["follow_up"]),
            )
        )
    lines.extend(
        [
            "",
            "## Вывод",
            "",
            "Канонический workspace foundation и перечисленное в разделах 1–16 "
            "поведение присутствуют в текущем коде и regression suite. Старый раздел "
            "«Следующий этап» больше не является актуальным backlog: character taxonomy, "
            "references, publications, analytics и team routes уже workspace-scoped.",
            "",
            "Оставшиеся действия разделены по типу, чтобы человеческая склонность "
            "называть всё одним словом «не готово» не испортила план:",
            "",
            "- `#561` — live owner/onboarding/destinations smoke, bounded slice `#410`;",
            "- `#562` — live role matrix и tenant callback isolation, bounded slice `#410`;",
            "- `#563` — provider-neutral personal quality, bounded code slice `#417`;",
            "- `#426` — video/animation subscriber notifications, существующий отдельный extension issue.",
            "",
            "Эти follow-up не отменяют подтвержденные core contracts и не закрываются "
            "зелёным CI автоматически.",
            "",
        ]
    )
    return "\n".join(lines)


def validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    source_path = ROOT / str(data.get("source", ""))
    if not source_path.is_file():
        errors.append(f"missing canonical source: {source_path.relative_to(ROOT)}")
        source = ""
    else:
        source = source_path.read_text(encoding="utf-8")

    rows = data.get("requirements", [])
    ids: set[str] = set()
    covered_sections: set[int] = set()
    for row in rows:
        row_id = str(row.get("id", ""))
        if not row_id:
            errors.append("requirement without id")
        elif row_id in ids:
            errors.append(f"duplicate requirement id: {row_id}")
        ids.add(row_id)

        status = str(row.get("status", ""))
        if status not in ALLOWED_STATUSES:
            errors.append(f"{row_id}: invalid status {status!r}")

        section = row.get("section")
        if isinstance(section, int):
            covered_sections.add(section)
        elif section is not None:
            errors.append(f"{row_id}: section must be integer or null")

        follow_up = row.get("follow_up", [])
        if status != "verified" and not follow_up:
            errors.append(f"{row_id}: follow-up status requires issue IDs")
        if any(not isinstance(issue, int) or issue <= 0 for issue in follow_up):
            errors.append(f"{row_id}: invalid follow-up issue")

        for field in ("implementation", "tests"):
            values = row.get(field, [])
            if not isinstance(values, list):
                errors.append(f"{row_id}: {field} must be a list")
                continue
            for raw in values:
                path = ROOT / str(raw)
                if not path.exists():
                    errors.append(f"{row_id}: missing {field} path {raw}")

    expected_sections = set(range(1, 17))
    if covered_sections != expected_sections:
        errors.append(
            "canonical section coverage mismatch: "
            f"missing={sorted(expected_sections - covered_sections)} "
            f"extra={sorted(covered_sections - expected_sections)}"
        )
    for section in expected_sections:
        if not re.search(rf"^## {section}\.\s", source, re.MULTILINE):
            errors.append(f"canonical source missing section {section}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render and validate workspace product gap audit"
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    data = _load()
    errors = validate(data)
    rendered = render(data)
    if args.write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(rendered, encoding="utf-8")
    if args.check:
        if not REPORT.is_file() or REPORT.read_text(encoding="utf-8") != rendered:
            errors.append("workspace_product_gap_audit.md is stale")
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
    if not args.write and not args.check:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
