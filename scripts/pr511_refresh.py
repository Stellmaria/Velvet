from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def replace_once(text: str, pattern: str, replacement: str, *, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"{label}: expected one replacement, got {count}")
    return updated


def patch_sources() -> None:
    worker = ROOT / "velvet_bot/domains/media_generation/friendly_worker.py"
    text = worker.read_text(encoding="utf-8")
    pattern = (
        r"        except Exception:\n"
        r"            logger\.exception\(\n"
        r"                \"Durable media recovery iteration failed phase=%s\",\n"
        r"                phase,\n"
        r"            \)\n"
    )
    replacement = '''        except Exception as error:  # p2-approved-boundary: isolate-durable-recovery-tick
            from velvet_bot.application.media_delivery import (
                classify_media_delivery_error,
                raise_if_programming_error,
            )

            failure = classify_media_delivery_error(
                error,
                phase=f"durable_recovery_{phase}",
            )
            logger.error(
                "durable_media_recovery_failed phase=%s code=%s fingerprint=%s",
                phase,
                failure.code,
                failure.fingerprint,
            )
            raise_if_programming_error(
                error,
                phase=f"durable_recovery_{phase}",
            )
'''
    if "p2-approved-boundary: isolate-durable-recovery-tick" not in text:
        text = replace_once(
            text,
            pattern,
            replacement,
            label="friendly_worker recovery boundary",
        )
        worker.write_text(text, encoding="utf-8")

    test = ROOT / "tests/test_media_delivery_failure_taxonomy.py"
    text = test.read_text(encoding="utf-8")
    text = text.replace(
        'self.assertIn("WHEN original_status=\'success\' THEN \'success\'", finish)',
        'self.assertIn("WHEN {status_column}=\'success\' THEN \'success\'", finish)',
    )
    text = text.replace(
        'self.assertIn("WHEN preview_status=\'success\' THEN \'success\'", finish)',
        'self.assertIn("{attempts_column}={attempts_column}+CASE", finish)',
    )
    test.write_text(text, encoding="utf-8")

    worklog = ROOT / "docs/worklog/2026-08-01-media-delivery-exception-taxonomy.md"
    text = worklog.read_text(encoding="utf-8")
    text = text.replace("- Статус: `в работе`", "- Статус: `завершено`")
    main_sha = subprocess.check_output(
        ["git", "rev-parse", "origin/main"],
        cwd=ROOT,
        text=True,
    ).strip()
    text = replace_once(
        text,
        r'- Базовый commit: `[^`]+`',
        f'- Базовый commit: `{main_sha}`',
        label="worklog base commit",
    )
    worklog.write_text(text, encoding="utf-8")


def refresh_inventories() -> None:
    run(
        sys.executable,
        "scripts/shared_contract_inventory.py",
        "--write-json",
        "docs/shared_contract_inventory.json",
        "--write-markdown",
        "docs/shared_contract_inventory.md",
    )
    run(
        sys.executable,
        "scripts/update_p2_stability_inventory.py",
        "--label",
        "p0-media-delivery-exception-taxonomy",
        "--schema-version",
        "75",
    )
    p2 = json.loads(
        (ROOT / "docs/p2_stability_inventory.json").read_text(encoding="utf-8")
    )
    unresolved = int(p2["broad_exception_unresolved"])
    if unresolved:
        raise RuntimeError(f"unresolved broad exceptions remain: {unresolved}")

    run(
        sys.executable,
        "scripts/inventory_package_architecture.py",
        "--write",
        "--bootstrap-exemptions",
        "--label",
        "p1-package-architecture-baseline",
    )


def update_architecture_expectations() -> None:
    data = json.loads(
        (ROOT / "docs/package_architecture_inventory.json").read_text(
            encoding="utf-8"
        )
    )
    shared = data["shared_contract_summary"]
    values = {
        "production_module_count": int(data["production_module_count"]),
        "production_loc": int(data["production_loc"]),
        "root_module_count": int(data["root_module_count"]),
        "router_count": int(data["router_count"]),
        "repository_module_count": int(data["repository_module_count"]),
        "installer_count": len(data["installer_graph"]),
        "violation_count": int(data["violation_count"]),
        "shared_files": int(shared["production_python_files"]),
        "shared_functions": int(shared["function_count"]),
        "shared_private": int(shared["private_contract_access_count"]),
        "shared_exact": int(shared["exact_duplicate_group_count"]),
        "shared_normalized": int(shared["normalized_duplicate_group_count"]),
        "shared_semantic": int(shared["semantic_near_duplicate_group_count"]),
    }
    path = ROOT / "tests/test_package_architecture_inventory.py"
    text = path.read_text(encoding="utf-8")
    substitutions = (
        (r'self\.assertEqual\(\d[\d_]*, self\.inventory\["production_module_count"\]\)', f'self.assertEqual({values["production_module_count"]:_}, self.inventory["production_module_count"])'),
        (r'self\.assertEqual\(\d[\d_]*, self\.inventory\["production_loc"\]\)', f'self.assertEqual({values["production_loc"]:_}, self.inventory["production_loc"])'),
        (r'self\.assertEqual\(\d[\d_]*, self\.inventory\["root_module_count"\]\)', f'self.assertEqual({values["root_module_count"]:_}, self.inventory["root_module_count"])'),
        (r'self\.assertEqual\(\d[\d_]*, self\.inventory\["router_count"\]\)', f'self.assertEqual({values["router_count"]:_}, self.inventory["router_count"])'),
        (r'self\.assertEqual\(\d[\d_]*, self\.inventory\["repository_module_count"\]\)', f'self.assertEqual({values["repository_module_count"]:_}, self.inventory["repository_module_count"])'),
        (r'self\.assertEqual\(\d[\d_]*, len\(self\.inventory\["installer_graph"\]\)\)', f'self.assertEqual({values["installer_count"]:_}, len(self.inventory["installer_graph"]))'),
        (r'self\.assertEqual\(\d[\d_]*, self\.inventory\["violation_count"\]\)', f'self.assertEqual({values["violation_count"]:_}, self.inventory["violation_count"])'),
        (r'self\.assertEqual\(\d[\d_]*, shared\["production_python_files"\]\)', f'self.assertEqual({values["shared_files"]:_}, shared["production_python_files"])'),
        (r'self\.assertEqual\(\d[\d_]*, shared\["function_count"\]\)', f'self.assertEqual({values["shared_functions"]:_}, shared["function_count"])'),
        (r'self\.assertEqual\(\d[\d_]*, shared\["private_contract_access_count"\]\)', f'self.assertEqual({values["shared_private"]:_}, shared["private_contract_access_count"])'),
        (r'self\.assertEqual\(\d[\d_]*, shared\["exact_duplicate_group_count"\]\)', f'self.assertEqual({values["shared_exact"]:_}, shared["exact_duplicate_group_count"])'),
        (r'self\.assertEqual\(\d[\d_]*, shared\["normalized_duplicate_group_count"\]\)', f'self.assertEqual({values["shared_normalized"]:_}, shared["normalized_duplicate_group_count"])'),
        (r'self\.assertEqual\(\d[\d_]*, shared\["semantic_near_duplicate_group_count"\]\)', f'self.assertEqual({values["shared_semantic"]:_}, shared["semantic_near_duplicate_group_count"])'),
        (r'self\.assertIn\("Production modules: \*\*\d+\*\*", self\.markdown\)', f'self.assertIn("Production modules: **{values["production_module_count"]}**", self.markdown)'),
        (r'self\.assertIn\("Production LOC: \*\*\d+\*\*", self\.markdown\)', f'self.assertIn("Production LOC: **{values["production_loc"]}**", self.markdown)'),
        (r'self\.assertIn\("Startup installer stages: \*\*\d+\*\*", self\.markdown\)', f'self.assertIn("Startup installer stages: **{values["installer_count"]}**", self.markdown)'),
        (r'self\.assertIn\("Registered package violations: \*\*\d+\*\*", self\.markdown\)', f'self.assertIn("Registered package violations: **{values["violation_count"]}**", self.markdown)'),
        (r'self\.assertIn\("Registered exemptions: \*\*\d+\*\*", self\.markdown\)', f'self.assertIn("Registered exemptions: **{values["violation_count"]}**", self.markdown)'),
    )
    for pattern, replacement in substitutions:
        text = replace_once(
            text,
            pattern,
            replacement,
            label=f"architecture expectation {pattern}",
        )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_sources()
    refresh_inventories()
    update_architecture_expectations()
    run(sys.executable, "-m", "compileall", "-q", "velvet_bot", "tests", "scripts")


if __name__ == "__main__":
    main()
