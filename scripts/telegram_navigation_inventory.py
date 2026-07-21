from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

BUTTON_NAMES = {"InlineKeyboardButton", "KeyboardButton"}
MARKUP_KEYWORDS = {"inline_keyboard", "keyboard"}
DYNAMIC_RISK_NAMES = {
    "name",
    "title",
    "label",
    "file",
    "story",
    "character",
    "universe",
    "category",
    "reason",
    "description",
    "display",
    "username",
}
PAGINATION_MARKERS = {"◀", "▶", "⬅", "➡"}
NAVIGATION_WORDS = ("назад", "главная", "закрыть", "меню", "аудит", "qwen")


@dataclass(frozen=True, slots=True)
class ButtonRecord:
    path: str
    line: int
    text: str
    static_length: int
    dynamic: bool
    row_size: int | None
    callback_literal: str | None
    source: str


@dataclass(frozen=True, slots=True)
class NavigationViolation:
    code: str
    path: str
    line: int
    detail: str


@dataclass(frozen=True, slots=True)
class NavigationInventory:
    files_scanned: int
    files_with_buttons: int
    button_count: int
    inline_button_count: int
    reply_button_count: int
    literal_callback_count: int
    max_row_size: int
    buttons: tuple[ButtonRecord, ...]
    violations: tuple[NavigationViolation, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class _Scanner(ast.NodeVisitor):
    def __init__(self, *, path: Path, root: Path, source: str) -> None:
        self.path = path
        self.root = root
        self.source = source
        self.parents: dict[ast.AST, ast.AST] = {}
        self.buttons: list[ButtonRecord] = []
        self.violations: list[NavigationViolation] = []
        self.max_row_size = 0

    def visit(self, node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            self.parents[child] = node
        super().visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        if name not in BUTTON_NAMES:
            self.generic_visit(node)
            return

        text_node = _argument(node, "text", position=0)
        callback_node = _argument(node, "callback_data", position=None)
        text, static_length, dynamic = _render_text(text_node)
        callback_literal = _constant_string(callback_node)
        row_size = self._row_size(node)
        source = ast.get_source_segment(self.source, node) or ""
        relative = self.path.relative_to(self.root).as_posix()
        record = ButtonRecord(
            path=relative,
            line=node.lineno,
            text=text,
            static_length=static_length,
            dynamic=dynamic,
            row_size=row_size,
            callback_literal=callback_literal,
            source=" ".join(source.split())[:500],
        )
        self.buttons.append(record)
        self._validate(record, text_node)
        self.generic_visit(node)

    def visit_keyword(self, node: ast.keyword) -> None:
        if node.arg in MARKUP_KEYWORDS and isinstance(node.value, (ast.List, ast.Tuple)):
            for row in node.value.elts:
                size = _literal_row_size(row)
                if size is None:
                    continue
                self.max_row_size = max(self.max_row_size, size)
                if size > 2 and not self._is_pagination_row(row):
                    relative = self.path.relative_to(self.root).as_posix()
                    self.violations.append(
                        NavigationViolation(
                            code="row_too_wide",
                            path=relative,
                            line=getattr(row, "lineno", node.lineno),
                            detail=f"Строка содержит {size} кнопки; допустимо 2, кроме пагинации.",
                        )
                    )
        self.generic_visit(node)

    def _row_size(self, node: ast.Call) -> int | None:
        parent = self.parents.get(node)
        if not isinstance(parent, (ast.List, ast.Tuple)):
            return None
        if not all(_is_button_call(item) for item in parent.elts):
            return None
        size = len(parent.elts)
        self.max_row_size = max(self.max_row_size, size)
        return size

    def _is_pagination_row(self, row: ast.AST) -> bool:
        if not isinstance(row, (ast.List, ast.Tuple)):
            return False
        labels: list[str] = []
        for item in row.elts:
            if not isinstance(item, ast.Call):
                return False
            text_node = _argument(item, "text", position=0)
            label = _constant_string(text_node)
            if label is None:
                rendered, _, dynamic = _render_text(text_node)
                if not dynamic:
                    label = rendered
                else:
                    label = rendered
            labels.append(label or "")
        combined = " ".join(labels)
        return any(marker in combined for marker in PAGINATION_MARKERS)

    def _validate(self, record: ButtonRecord, text_node: ast.AST | None) -> None:
        path = record.path
        if not record.dynamic:
            limit = 24 if record.row_size == 2 else 32
            if record.static_length > limit:
                self.violations.append(
                    NavigationViolation(
                        code="label_too_long",
                        path=path,
                        line=record.line,
                        detail=(
                            f"Подпись длиной {record.static_length}, лимит {limit}: "
                            f"{record.text!r}"
                        ),
                    )
                )
        elif _dynamic_text_is_risky(text_node) and not _has_bounded_slice(text_node):
            self.violations.append(
                NavigationViolation(
                    code="dynamic_label_unbounded",
                    path=path,
                    line=record.line,
                    detail=f"Динамическая подпись без явной обрезки: {record.text!r}",
                )
            )

        if record.callback_literal is not None:
            size = len(record.callback_literal.encode("utf-8"))
            if size > 64:
                self.violations.append(
                    NavigationViolation(
                        code="callback_too_long",
                        path=path,
                        line=record.line,
                        detail=f"callback_data занимает {size} байт.",
                    )
                )

        folded = record.text.casefold()
        if record.text.startswith("↩") and not any(word in folded for word in NAVIGATION_WORDS):
            self.violations.append(
                NavigationViolation(
                    code="unclear_back_label",
                    path=path,
                    line=record.line,
                    detail=f"Непонятная кнопка возврата: {record.text!r}",
                )
            )


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _argument(call: ast.Call, name: str, *, position: int | None) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    if position is not None and len(call.args) > position:
        return call.args[position]
    return None


def _constant_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _render_text(node: ast.AST | None) -> tuple[str, int, bool]:
    if node is None:
        return "<missing>", 0, True
    value = _constant_string(node)
    if value is not None:
        return value, len(value), False
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        static_length = 0
        for item in node.values:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                parts.append(item.value)
                static_length += len(item.value)
            else:
                parts.append("{…}")
        return "".join(parts), static_length, True
    if isinstance(node, ast.Subscript):
        rendered, static_length, dynamic = _render_text(node.value)
        return rendered, static_length, dynamic
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, left_length, left_dynamic = _render_text(node.left)
        right, right_length, right_dynamic = _render_text(node.right)
        return left + right, left_length + right_length, left_dynamic or right_dynamic
    return "<dynamic>", 0, True


def _dynamic_text_is_risky(node: ast.AST | None) -> bool:
    if node is None:
        return False
    target = node.value if isinstance(node, ast.Subscript) else node
    if not isinstance(target, ast.JoinedStr):
        return False
    names: set[str] = set()
    for item in ast.walk(target):
        if isinstance(item, ast.Name):
            names.add(item.id.casefold())
        elif isinstance(item, ast.Attribute):
            names.add(item.attr.casefold())
    return any(any(risk in name for risk in DYNAMIC_RISK_NAMES) for name in names)


def _has_bounded_slice(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Subscript):
        return False
    slice_node = node.slice
    if isinstance(slice_node, ast.Slice):
        upper = slice_node.upper
        return isinstance(upper, ast.Constant) and isinstance(upper.value, int) and upper.value <= 64
    return False


def _is_button_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node.func) in BUTTON_NAMES


def _literal_row_size(node: ast.AST) -> int | None:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    if not node.elts or not all(_is_button_call(item) for item in node.elts):
        return None
    return len(node.elts)


def _python_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def scan_repository(root: Path) -> NavigationInventory:
    root = root.resolve()
    files = list(_python_files(root))
    buttons: list[ButtonRecord] = []
    violations: list[NavigationViolation] = []
    files_with_buttons: set[str] = set()
    max_row_size = 0

    for path in files:
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=path.as_posix())
        except SyntaxError as error:
            violations.append(
                NavigationViolation(
                    code="syntax_error",
                    path=path.relative_to(root).as_posix(),
                    line=error.lineno or 0,
                    detail=str(error),
                )
            )
            continue
        scanner = _Scanner(path=path, root=root, source=source)
        scanner.visit(tree)
        if scanner.buttons:
            files_with_buttons.add(path.relative_to(root).as_posix())
        buttons.extend(scanner.buttons)
        violations.extend(scanner.violations)
        max_row_size = max(max_row_size, scanner.max_row_size)

    return NavigationInventory(
        files_scanned=len(files),
        files_with_buttons=len(files_with_buttons),
        button_count=len(buttons),
        inline_button_count=sum("InlineKeyboardButton" in item.source for item in buttons),
        reply_button_count=sum("KeyboardButton" in item.source and "InlineKeyboardButton" not in item.source for item in buttons),
        literal_callback_count=sum(item.callback_literal is not None for item in buttons),
        max_row_size=max_row_size,
        buttons=tuple(buttons),
        violations=tuple(
            sorted(violations, key=lambda item: (item.path, item.line, item.code))
        ),
    )


def render_markdown(inventory: NavigationInventory) -> str:
    lines = [
        "# Telegram navigation inventory",
        "",
        f"- Python files scanned: **{inventory.files_scanned}**",
        f"- Files with buttons: **{inventory.files_with_buttons}**",
        f"- Buttons: **{inventory.button_count}**",
        f"- Inline buttons: **{inventory.inline_button_count}**",
        f"- Reply buttons: **{inventory.reply_button_count}**",
        f"- Maximum literal row size: **{inventory.max_row_size}**",
        f"- Violations: **{len(inventory.violations)}**",
        "",
        "## Violations",
        "",
    ]
    if not inventory.violations:
        lines.append("No violations.")
    else:
        for item in inventory.violations:
            lines.append(
                f"- `{item.code}` `{item.path}:{item.line}` — {item.detail}"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("velvet_bot"))
    parser.add_argument("--json", dest="json_path", type=Path)
    parser.add_argument("--markdown", dest="markdown_path", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    inventory = scan_repository(args.root)
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(
            json.dumps(inventory.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    markdown = render_markdown(inventory)
    if args.markdown_path:
        args.markdown_path.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_path.write_text(markdown, encoding="utf-8")
    else:
        print(markdown, end="")
    return 1 if args.check and inventory.violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
