from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
WORKLOG_DIR = ROOT / "docs" / "worklog"
REQUIRED_FILES = (
    ROOT / "AGENTS.md",
    ROOT / "docs" / "project_memory.md",
    ROOT / "docs" / "development_status.md",
    WORKLOG_DIR / "README.md",
)
REQUIRED_HEADINGS = (
    "## Перед началом",
    "### Цель",
    "### Исходный контекст",
    "### Планируемый объём",
    "### Критерии готовности",
    "### Риски и ограничения",
    "## После завершения",
    "### Фактически сделано",
    "### Миграции и совместимость",
    "### Проверки",
    "### PR и commit",
    "### Незавершённое",
    "### Следующий шаг",
)
FINAL_STATUSES = {"завершено", "частично", "заблокировано"}
WORKLOG_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*\.md$")
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:BOT_TOKEN|SUPERVISOR_TOKEN|API_KEY|PASSWORD)\s*[=:]\s*\S+"),
    re.compile(r"(?i)\b(?:postgres(?:ql)?|redis|mysql|mongodb(?:\+srv)?)://[^\s/]+:[^\s/@]+@\S+"),
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b"),
)


class NotesContractError(RuntimeError):
    pass


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _status(text: str) -> str | None:
    match = re.search(r"(?mi)^- Статус:\s*(?:`([^`]+)`|([^\n]+))\s*$", text)
    if match is None:
        return None
    return (match.group(1) or match.group(2) or "").strip().casefold()


def validate_worklog(path: Path, *, require_final: bool = True) -> list[str]:
    errors: list[str] = []
    if path.name == "README.md":
        return errors
    if not WORKLOG_NAME_RE.fullmatch(path.name):
        errors.append(f"{path}: имя должно соответствовать YYYY-MM-DD-slug.md")
    text = _read(path)
    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"{path}: отсутствует раздел {heading!r}")
    for field in ("- Дата:", "- ID:", "- Линия/фаза:", "- Статус:", "- Ветка:", "- Базовый commit:"):
        if field not in text:
            errors.append(f"{path}: отсутствует поле {field}")
    status = _status(text)
    if status is None:
        errors.append(f"{path}: не удалось прочитать статус")
    elif require_final and status not in FINAL_STATUSES:
        errors.append(
            f"{path}: перед CI статус должен быть одним из {sorted(FINAL_STATUSES)}, получено {status!r}"
        )
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            errors.append(f"{path}: найдено значение, похожее на секрет")
            break
    return errors


def validate_repository(*, require_final: bool = True) -> list[str]:
    errors: list[str] = []
    for path in REQUIRED_FILES:
        if not path.exists():
            errors.append(f"отсутствует обязательный файл: {path.relative_to(ROOT)}")
    if not WORKLOG_DIR.exists():
        return errors
    entries = sorted(path for path in WORKLOG_DIR.glob("*.md") if path.name != "README.md")
    if not entries:
        errors.append("docs/worklog не содержит ни одной рабочей сессии")
    for path in entries:
        errors.extend(validate_worklog(path, require_final=require_final))
    memory = ROOT / "docs" / "project_memory.md"
    if memory.exists():
        text = _read(memory)
        for heading in (
            "# Линия A. Основное развитие текущего Velvet Archive",
            "# Линия B. Velvet AI / Qwen",
            "# Линия C. Исторический план раннего рефакторинга",
            "# Открытые обязательства",
        ):
            if heading not in text:
                errors.append(f"docs/project_memory.md: отсутствует раздел {heading!r}")
    agents = ROOT / "AGENTS.md"
    if agents.exists():
        text = _read(agents)
        if "## Перед началом работы" not in text or "## После завершения работы" not in text:
            errors.append("AGENTS.md не содержит обязательный цикл до/после работы")
    return errors


def _git_changed_files(base_ref: str) -> tuple[str, ...]:
    command = ("git", "diff", "--name-only", f"{base_ref}...HEAD")
    completed = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode:
        raise NotesContractError(
            f"Не удалось определить изменённые файлы: {' '.join(command)}\n{completed.stdout}"
        )
    return tuple(line.strip() for line in completed.stdout.splitlines() if line.strip())


def validate_changed_files(paths: Iterable[str]) -> list[str]:
    changed = tuple(paths)
    meaningful = tuple(
        path
        for path in changed
        if path not in {"docs/worklog/README.md"}
        and not path.startswith(".github/workflows/project-notes-contract")
    )
    if not meaningful:
        return []
    worklogs = tuple(
        path
        for path in changed
        if path.startswith("docs/worklog/") and path.endswith(".md") and not path.endswith("/README.md")
    )
    if not worklogs:
        return [
            "Содержательный PR обязан добавить или изменить отдельную запись docs/worklog/YYYY-MM-DD-slug.md"
        ]
    errors: list[str] = []
    for relative in worklogs:
        path = ROOT / relative
        if not path.exists():
            errors.append(f"Рабочая запись удалена или недоступна: {relative}")
            continue
        errors.extend(validate_worklog(path, require_final=True))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Проверка проектной памяти и рабочего журнала Velvet")
    parser.add_argument("--base-ref", help="Git ref базовой ветки для проверки изменённых файлов")
    parser.add_argument(
        "--allow-in-progress",
        action="store_true",
        help="Разрешить статус 'в работе' при локальной подготовке, но не перед merge",
    )
    args = parser.parse_args(argv)

    errors = validate_repository(require_final=not args.allow_in_progress)
    if args.base_ref:
        try:
            errors.extend(validate_changed_files(_git_changed_files(args.base_ref)))
        except NotesContractError as error:
            errors.append(str(error))

    if errors:
        print("Project notes contract failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Project notes contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
