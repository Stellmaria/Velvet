from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "velvet_bot"
# Audit both current sources and historical refs because the missing screen may
# survive only on an old development branch.
SCREENSHOT_LABELS = (
    "Проверить новое изображение",
    "Очередь ошибок",
    "Поиск дублей",
    "Медиасеты",
    "Проверить последние файлы",
    "Запустить проверку",
    "Повторить ошибки",
    "Управление фоновыми проверками архива и поиск проблем",
)


@dataclass(frozen=True)
class CommandEntry:
    file: str
    line: int
    function: str
    commands: tuple[str, ...]


@dataclass(frozen=True)
class ButtonEntry:
    file: str
    line: int
    text: str
    callback: str


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def literal_text(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


def scan_python() -> tuple[list[CommandEntry], list[ButtonEntry]]:
    commands: list[CommandEntry] = []
    buttons: list[ButtonEntry] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found: list[str] = []
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call):
                        continue
                    if not dotted_name(decorator.func).endswith(".message"):
                        continue
                    for arg in decorator.args:
                        if not isinstance(arg, ast.Call):
                            continue
                        filter_name = dotted_name(arg.func)
                        if filter_name.endswith("Command"):
                            for command_arg in arg.args:
                                if isinstance(command_arg, ast.Constant) and isinstance(command_arg.value, str):
                                    found.append(command_arg.value)
                        elif filter_name.endswith("CommandStart"):
                            found.append("start")
                if found:
                    commands.append(
                        CommandEntry(relative, node.lineno, node.name, tuple(dict.fromkeys(found)))
                    )
            if isinstance(node, ast.Call) and dotted_name(node.func).endswith("InlineKeyboardButton"):
                kwargs = {item.arg: item.value for item in node.keywords if item.arg}
                text = literal_text(kwargs.get("text"))
                callback = literal_text(kwargs.get("callback_data"))
                buttons.append(ButtonEntry(relative, node.lineno, text, callback))
    return commands, buttons


def git_locations(label: str) -> list[str]:
    refs_raw = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    results: list[str] = []
    for ref in dict.fromkeys(line.strip() for line in refs_raw.splitlines() if line.strip()):
        process = subprocess.run(
            ["git", "grep", "-n", "-F", label, ref, "--", "*.py"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if process.returncode == 0:
            for line in process.stdout.splitlines():
                results.append(line)
                if len(results) >= 30:
                    return results
    return results


def main() -> None:
    commands, buttons = scan_python()
    quality_commands = [
        item for item in commands
        if any(
            token in " ".join(item.commands).casefold()
            for token in ("quality", "audit", "scan", "duplicate", "set", "vision", "ai", "check")
        )
        or any(token in item.file.casefold() for token in ("quality", "vision", "duplicate", "media_set", "ai"))
    ]
    quality_buttons = [
        item for item in buttons
        if any(
            token in f"{item.text} {item.callback} {item.file}".casefold()
            for token in (
                "quality", "qcheck", "scan", "дубл", "медиасет", "setreport", "vision",
                "провер", "ошиб", "ai_menu", "velvet ai", "палитр", "референс",
            )
        )
    ]

    lines = [
        "# Аудит команд и кнопок Velvet",
        "",
        f"Всего slash-обработчиков: **{len(commands)}**",
        f"Всего найденных кнопок: **{len(buttons)}**",
        "",
        "## Все slash-команды",
        "",
    ]
    for item in commands:
        lines.append(
            f"- `/{'`, `/'.join(item.commands)}` → `{item.function}` "
            f"(`{item.file}:{item.line}`)"
        )

    lines.extend(["", "## Команды качества и AI", ""])
    for item in quality_commands:
        lines.append(
            f"- `/{'`, `/'.join(item.commands)}` → `{item.function}` "
            f"(`{item.file}:{item.line}`)"
        )
    if not quality_commands:
        lines.append("- Не найдены отдельные slash-команды качества/AI.")

    lines.extend(["", "## Кнопки качества и AI", ""])
    for item in quality_buttons:
        lines.append(
            f"- **{item.text}** → `{item.callback}` (`{item.file}:{item.line}`)"
        )

    lines.extend(["", "## История кнопок со скриншота", ""])
    for label in SCREENSHOT_LABELS:
        locations = git_locations(label)
        lines.append(f"### {label}")
        if locations:
            lines.extend(f"- `{location}`" for location in locations)
        else:
            lines.append("- Не найдено ни в одной доступной ветке.")
        lines.append("")

    (ROOT / "menu_coverage_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
