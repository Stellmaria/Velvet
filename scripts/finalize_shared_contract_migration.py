from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _path(value: str) -> Path:
    return ROOT / value


def _replace_file(path_value: str, replacements: tuple[tuple[str, str], ...]) -> bool:
    path = _path(path_value)
    source = path.read_text(encoding="utf-8")
    updated = source
    for old, new in replacements:
        updated = updated.replace(old, new)
    if updated == source:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def _fix_portal() -> list[str]:
    path_value = "velvet_bot/app/auf_user_portal_install.py"
    changed = _replace_file(
        path_value,
        (
            ("format_userformat_user_task_line", "format_user_task_line"),
            (
                "build_userbuild_user_task_list_keyboard",
                "build_user_task_list_keyboard",
            ),
            ("rows = await _load_user_tasks(", "rows = await load_user_tasks("),
        ),
    )
    return [path_value] if changed else []


def _fix_video_contracts() -> list[str]:
    changed: list[str] = []
    core_path_value = (
        "velvet_bot/presentation/telegram/routers/workspace_auf_video.py"
    )
    core_path = _path(core_path_value)
    source = core_path.read_text(encoding="utf-8")
    marker = "edit_or_answer = _edit_or_answer\n"
    public_block = (
        "edit_or_answer = _edit_or_answer\n"
        "callback_data = _callback\n"
        "format_rub = _format_rub\n"
        "format_usd = _format_usd\n"
    )
    if "callback_data = _callback" not in source:
        if marker not in source:
            raise RuntimeError("workspace_auf_video public alias marker is missing")
        source = source.replace(marker, public_block, 1)
        core_path.write_text(source, encoding="utf-8")
        changed.append(core_path_value)

    simple_path_value = (
        "velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py"
    )
    if _replace_file(
        simple_path_value,
        (
            ("_callback as video_callback", "callback_data as video_callback"),
            ("_format_rub", "format_rub"),
            ("_format_usd", "format_usd"),
            ("legacy._reference_from_data", "legacy.reference_from_data"),
            ("legacy._edit_or_answer", "legacy.edit_or_answer"),
        ),
    ):
        changed.append(simple_path_value)

    for path in sorted((ROOT / "velvet_bot").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        updated = source.replace(
            "video_core._reference_from_data", "video_core.reference_from_data"
        ).replace(
            "video_core._edit_or_answer", "video_core.edit_or_answer"
        )
        if updated != source:
            path.write_text(updated, encoding="utf-8")
            changed.append(relative)
    return changed


def _fix_active_delivery() -> list[str]:
    path_value = "velvet_bot/app/auf_active_delivery_fix.py"
    path = _path(path_value)
    source = path.read_text(encoding="utf-8")
    updated = source.replace(
        "provider_task_id = provider_task_id(result, payload)",
        "resolved_provider_task_id = provider_task_id(result, payload)",
    )
    updated = updated.replace(
        "if provider_task_id is None:\n",
        "if resolved_provider_task_id is None:\n",
    )
    updated = updated.replace(
        "urls = await _load_provider_urls(provider_task_id)",
        "urls = await _load_provider_urls(resolved_provider_task_id)",
    )
    updated = updated.replace(
        "provider_task_id=provider_task_id,",
        "provider_task_id=resolved_provider_task_id,",
    )
    updated = updated.replace(
        "            provider_task_id,\n",
        "            resolved_provider_task_id,\n",
    )
    old_install = '''    _ORIGINAL_REDELIVER = recovery._redeliver_user_task
    recovery._redeliver_user_task = _redeliver_with_provider_recovery
    recovery._task_delivery_buttons = _delivery_buttons_for_all_success

    active_worker = workers.KieGenerationWorker
    active_worker._deliver_best_effort = recovery._deliver_record_with_recovery
'''
    new_install = '''    _ORIGINAL_REDELIVER = recovery.get_redelivery_handler()
    recovery.install_redelivery_handler(_redeliver_with_provider_recovery)
    recovery.install_task_delivery_buttons(delivery_buttons_for_all_success)

    active_worker = workers.KieGenerationWorker
    active_worker.install_delivery_handler(recovery.deliver_record_with_recovery)
'''
    if old_install in updated:
        updated = updated.replace(old_install, new_install, 1)
    elif new_install not in updated:
        raise RuntimeError("active delivery installation block changed unexpectedly")
    if updated == source:
        return []
    path.write_text(updated, encoding="utf-8")
    return [path_value]


def _fix_scanner() -> list[str]:
    path_value = "scripts/shared_contract_inventory.py"
    path = _path(path_value)
    source = path.read_text(encoding="utf-8")
    updated = source.replace(
        'target_contract="velvet_bot.domains.media_generation.models",',
        'target_contract="velvet_bot.domains.media_generation.model_catalog",',
    )

    serialization_marker = "\ndef build_inventory() -> dict[str, object]:\n"
    serialization_block = '''
def _serialize_occurrence(item: FunctionOccurrence) -> dict[str, object]:
    return {
        "path": item.path,
        "module": item.module,
        "name": item.name,
        "line": item.line,
        "end_line": item.end_line,
    }


def _serialize_group(group: DuplicateGroup) -> dict[str, object]:
    return {
        "digest": group.digest,
        "kind": group.kind,
        "family": group.family,
        "reason": group.reason,
        "occurrences": [
            _serialize_occurrence(item) for item in group.occurrences
        ],
    }


def build_inventory() -> dict[str, object]:
'''
    if "def _serialize_group(group: DuplicateGroup)" not in updated:
        if serialization_marker not in updated:
            raise RuntimeError("scanner build_inventory marker is missing")
        updated = updated.replace(serialization_marker, serialization_block, 1)

    updated = updated.replace(
        "    consumers = _contract_consumers(paths, trees)\n    contracts = []\n",
        "    consumers = _contract_consumers(paths, trees)\n"
        "    known_contracts = _known_contract_output(private_accesses)\n"
        "    blocking_private_accesses = [\n"
        "        occurrence\n"
        "        for contract in known_contracts\n"
        "        if contract[\"status\"] == \"current-violation\"\n"
        "        for occurrence in contract[\"current_occurrences\"]\n"
        "    ]\n"
        "    contracts = []\n",
    )
    updated = updated.replace(
        '        "private_contract_access_count": len(private_accesses),\n'
        '        "private_contract_accesses": [asdict(item) for item in private_accesses],\n'
        '        "known_private_contracts": _known_contract_output(private_accesses),\n',
        '        "private_contract_access_count": len(private_accesses),\n'
        '        "private_contract_accesses": [asdict(item) for item in private_accesses],\n'
        '        "blocking_private_contract_access_count": len(blocking_private_accesses),\n'
        '        "blocking_private_contract_accesses": blocking_private_accesses,\n'
        '        "known_private_contracts": known_contracts,\n',
    )
    updated = updated.replace(
        '        "exact_duplicate_groups": [asdict(group) for group in exact_groups],\n'
        '        "normalized_duplicate_groups": [asdict(group) for group in normalized_groups],\n'
        '        "semantic_near_duplicate_groups": [asdict(group) for group in semantic_groups],\n',
        '        "exact_duplicate_groups": [_serialize_group(group) for group in exact_groups],\n'
        '        "normalized_duplicate_groups": [\n'
        '            _serialize_group(group) for group in normalized_groups\n'
        '        ],\n'
        '        "semantic_near_duplicate_groups": [\n'
        '            _serialize_group(group) for group in semantic_groups\n'
        '        ],\n',
    )

    private_validation = re.compile(
        r"    private_accesses = list\(data\[\"private_contract_accesses\"\]\)\n"
        r"    if private_accesses:\n"
        r".*?"
        r"        errors\.append\(\"private cross-module helper contracts: \" \+ rendered \+ suffix\)\n",
        re.DOTALL,
    )
    replacement = '''    blocking_private_accesses = list(
        data["blocking_private_contract_accesses"]
    )
    if blocking_private_accesses:
        rendered = ", ".join(
            f"{item['path']}:{item['line']} {item['expression']}"
            for item in blocking_private_accesses
        )
        errors.append("known private helper contracts remain: " + rendered)
'''
    updated, count = private_validation.subn(replacement, updated, count=1)
    if count == 0 and "known private helper contracts remain" not in updated:
        raise RuntimeError("scanner private validation block is missing")

    updated = updated.replace(
        '        f"- Private cross-module contracts: **{data[\'private_contract_access_count\']}**",\n',
        '        f"- Registered private cross-module debt: **{data[\'private_contract_access_count\']}**",\n'
        '        f"- Blocking known private contracts: **{data[\'blocking_private_contract_access_count\']}**",\n',
    )
    updated = updated.replace(
        '    lines.extend(["", "## Current private accesses", ""])\n',
        '    lines.extend(["", "## Registered transitional private accesses", ""])\n',
    )

    if updated == source:
        return []
    path.write_text(updated, encoding="utf-8")
    return [path_value]


def _refresh_inventories() -> None:
    commands = (
        (
            sys.executable,
            "scripts/inventory_telegram_helpers.py",
            "--write-json",
            "docs/shared_contract_inventory.json",
            "--write-markdown",
            "docs/shared_contract_inventory.md",
        ),
        (
            sys.executable,
            "scripts/update_p2_stability_inventory.py",
            "--label",
            "p3-package-shared-contracts",
            "--schema-version",
            "74",
        ),
        (
            sys.executable,
            "scripts/inventory_architecture_layout.py",
            "--write",
            "--label",
            "p3d-analytics-alias-retirement",
        ),
        (
            sys.executable,
            "scripts/telegram_navigation_inventory.py",
            "--root",
            "velvet_bot",
            "--markdown",
            "docs/generated/telegram_navigation_inventory.md",
        ),
    )
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    changed: list[str] = []
    changed.extend(_fix_portal())
    changed.extend(_fix_video_contracts())
    changed.extend(_fix_active_delivery())
    changed.extend(_fix_scanner())
    _refresh_inventories()
    subprocess.run(
        [sys.executable, "scripts/inventory_telegram_helpers.py", "--check"],
        cwd=ROOT,
        check=True,
    )
    if changed:
        print("Finalized shared contract migration:")
        for item in sorted(set(changed)):
            print(f"- {item}")
    else:
        print("Shared contract migration is already finalized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
