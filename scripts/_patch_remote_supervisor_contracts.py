from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INLINE = ROOT / "tests/test_inline_management_menus.py"
INTEGRITY = ROOT / "tests/test_project_integrity.py"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: ожидалось одно совпадение, найдено {count}")
    return source.replace(old, new, 1)


def patch_inline() -> None:
    source = INLINE.read_text(encoding="utf-8")
    source = replace_once(
        source,
        '            SupervisorCallback(action="codex.menu").pack(),\n'
        '            SupervisorCallback(action="status").pack(),\n',
        '            SupervisorCallback(action="codex.menu").pack(),\n'
        '            SupervisorCallback(action="console.menu").pack(),\n'
        '            SupervisorCallback(action="self.menu").pack(),\n'
        '            SupervisorCallback(action="status").pack(),\n',
        "supervisor sections",
    )
    source = replace_once(
        source,
        '        task_message = SimpleNamespace(\n'
        '            reply_to_message=SimpleNamespace(\n'
        '                text=None,\n'
        '                caption="SUPERVISOR_INPUT:task",\n'
        '            )\n'
        '        )\n'
        '        unrelated = SimpleNamespace(\n',
        '        task_message = SimpleNamespace(\n'
        '            reply_to_message=SimpleNamespace(\n'
        '                text=None,\n'
        '                caption="SUPERVISOR_INPUT:task",\n'
        '            )\n'
        '        )\n'
        '        console_message = SimpleNamespace(\n'
        '            reply_to_message=SimpleNamespace(\n'
        '                text="SUPERVISOR_INPUT:console",\n'
        '                caption=None,\n'
        '            )\n'
        '        )\n'
        '        unrelated = SimpleNamespace(\n',
        "console reply fixture",
    )
    source = replace_once(
        source,
        '        self.assertEqual(\n'
        '            asyncio.run(filter_(task_message)),\n'
        '            {"supervisor_input_kind": "task"},\n'
        '        )\n'
        '        self.assertFalse(asyncio.run(filter_(unrelated)))\n',
        '        self.assertEqual(\n'
        '            asyncio.run(filter_(task_message)),\n'
        '            {"supervisor_input_kind": "task"},\n'
        '        )\n'
        '        self.assertEqual(\n'
        '            asyncio.run(filter_(console_message)),\n'
        '            {"supervisor_input_kind": "console"},\n'
        '        )\n'
        '        self.assertFalse(asyncio.run(filter_(unrelated)))\n',
        "console reply assertion",
    )
    ast.parse(source, filename=str(INLINE))
    INLINE.write_text(source, encoding="utf-8")


def patch_integrity() -> None:
    source = INTEGRITY.read_text(encoding="utf-8")
    source = replace_once(
        source,
        '    "codex_status",\n'
        '}\n'
        'FORM_COMMANDS = {\n',
        '    "codex_status",\n'
        '    "console",\n'
        '    "supervisor_console",\n'
        '    "supervisor_self",\n'
        '}\n'
        'FORM_COMMANDS = {\n',
        "remote supervisor commands",
    )
    ast.parse(source, filename=str(INTEGRITY))
    INTEGRITY.write_text(source, encoding="utf-8")


def main() -> None:
    patch_inline()
    patch_integrity()


if __name__ == "__main__":
    main()
