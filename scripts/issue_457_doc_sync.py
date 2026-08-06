from __future__ import annotations

from pathlib import Path

_START = "<!-- issue-457-legacy-delivery-retirement -->"
_END = "<!-- /issue-457-legacy-delivery-retirement -->"
_BLOCK = """<!-- issue-457-legacy-delivery-retirement -->
## Retirement legacy media delivery installers — 6 августа 2026 года

Durable media delivery PR #488 остаётся единственным production ownership path. Четыре neutralized installer слоя удалены из startup composition; runtime method replacement `install_delivery_handler` удалён; active Friendly worker сохраняет явный no-op для inherited legacy delivery phase.

Воспроизводимый baseline current feature head:

- package production modules: **655**;
- inventoried functions: **3830**;
- registered transitional private accesses: **180**;
- blocking known contracts: **0**;
- startup installer stages: **21**;
- registered package architecture fingerprints: **521**.

Repository implementation #457 завершена этим срезом, но live provider/Telegram acceptance остаётся #410/#412. Зелёный CI не подтверждает production restart, CDN/expired URL или no-double-charge matrix.
<!-- /issue-457-legacy-delivery-retirement -->"""


def _replace_block(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    left = content.find(_START)
    right = content.find(_END, left)
    if left < 0 or right < 0:
        raise SystemExit(f"{path}: issue-457 marker block missing")
    right += len(_END)
    path.write_text(content[:left] + _BLOCK + content[right:], encoding="utf-8")


def main() -> None:
    for path_text in (
        "docs/development_status.md",
        "docs/project_memory.md",
        "docs/ARCHITECTURE_AUDIT.md",
    ):
        _replace_block(Path(path_text))

    worklog = Path(
        "docs/worklog/2026-08-06-retire-legacy-media-delivery-installers.md"
    )
    content = worklog.read_text(encoding="utf-8")
    old = "- legacy UI tests перенесены на canonical module;\n"
    new = (
        "- legacy UI tests перенесены на canonical module;\n"
        "- image/video/recovery assertions перенесены с удалённых modules на "
        "`TelegramMediaDeliveryTransport` и durable use cases;\n"
    )
    if content.count(old) != 1:
        raise SystemExit("worklog test migration marker missing")
    worklog.write_text(content.replace(old, new, 1), encoding="utf-8")


if __name__ == "__main__":
    main()
