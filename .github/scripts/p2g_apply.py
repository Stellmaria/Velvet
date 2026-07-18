from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[2]
bootstrap = root / "velvet_bot/app/bootstrap.py"
text = bootstrap.read_text(encoding="utf-8")
replacements = {
    '        except Exception:\n            logger.exception("Could not stop all background workers")': '        except Exception:  # p2-approved-boundary: isolate-worker-shutdown\n            logger.exception("Could not stop all background workers")',
    '        except Exception as error:\n            logger.warning("Could not send shutdown audit message: %s", error)': '        except Exception as error:  # p2-approved-boundary: best-effort-shutdown-audit\n            logger.warning("Could not send shutdown audit message: %s", error)',
    '        except Exception:\n            logger.exception("Could not stop error incident center")': '        except Exception:  # p2-approved-boundary: isolate-error-center-shutdown\n            logger.exception("Could not stop error incident center")',
    '        except Exception:\n            logger.exception("Could not close Telegram bot session")': '        except Exception:  # p2-approved-boundary: isolate-bot-session-shutdown\n            logger.exception("Could not close Telegram bot session")',
    '    except Exception:\n        logger.exception("Could not close PostgreSQL pool")': '    except Exception:  # p2-approved-boundary: isolate-database-shutdown\n        logger.exception("Could not close PostgreSQL pool")',
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(old)
    text = text.replace(old, new, 1)
bootstrap.write_text(text, encoding="utf-8")

reasons = {
    85: "isolate-worker-shutdown",
    91: "best-effort-shutdown-audit",
    99: "isolate-error-center-shutdown",
    105: "isolate-bot-session-shutdown",
    110: "isolate-database-shutdown",
}
inv_path = root / "docs/p2_stability_inventory.json"
data = json.loads(inv_path.read_text(encoding="utf-8"))
for item in data["broad_exceptions"]:
    if item["path"] == "velvet_bot/app/bootstrap.py" and item["function"] == "_close_application_resources":
        item["classification"] = "approved_boundary"
        item["reason"] = reasons[item["line"]]

approved = [item for item in data["broad_exceptions"] if item["classification"] == "approved_boundary"]
unresolved = [item for item in data["broad_exceptions"] if item["classification"] == "unresolved"]
data.update(
    schema_version=9,
    generated_from_commit="p2g-bootstrap-cleanup-boundaries",
    broad_exception_approved=len(approved),
    broad_exception_unresolved=len(unresolved),
    broad_exception_unresolved_files=len({item["path"] for item in unresolved}),
    next_slice={"target": "velvet_bot/app/bootstrap.py", "kind": "fatal_boundary_triage"},
)
inv_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

by_file = Counter(item["path"] for item in unresolved)
lines = [
    "# P2 stability inventory", "",
    "AST-инвентаризация широких исключений и callback acknowledgment.", "",
    "## Сводка", "",
    f"- broad exceptions raw: **{data['broad_exception_total']}** в **{data['broad_exception_files']}** файлах;",
    f"- approved orchestration boundaries: **{len(approved)}**;",
    f"- unresolved broad exceptions: **{len(unresolved)}** в **{len(by_file)}** файлах;",
    f"- callback handlers: **{data['callback_total']}**;",
    f"- missing/late acknowledgment: **{data['risky_callback_total']}**;",
    f"- guarded acknowledgment: **{data['guarded_callback_total']}**;",
    f"- delegated wrappers: **{data['delegated_callback_total']}**.", "",
    "## Approved broad boundaries", "",
]
for item in approved:
    lines.append(f"- `{item['path']}:{item['line']}` `{item['function']}`: {item['reason']}.")
lines += ["", "## Unresolved broad exceptions by file", ""]
for path, count in by_file.most_common():
    lines.append(f"- `{path}`: {count}.")
lines += [
    "", "## Risky callbacks", "",
    "- Нет. Callback late/missing baseline закрыт.", "",
    "## Следующий срез", "",
    "- `velvet_bot/app/bootstrap.py`: fatal reporting boundaries в `run_application()`.", "",
    "## Правило обновления", "",
    "Approved boundary требует inline-маркер и отдельный поведенческий тест. Raw count не уменьшается от классификации; unresolved count отражает оставшийся долг.", "",
]
(root / "docs/p2_stability_inventory.md").write_text("\n".join(lines), encoding="utf-8")

old = "3. P2F: AI job tracker compensation boundary классифицирован; unresolved broad baseline 64 → 63."
new = "3. P2G: bootstrap cleanup boundaries классифицированы; unresolved broad baseline 63 → 58."
for name in ("development_status.md", "project_memory.md"):
    path = root / "docs" / name
    value = path.read_text(encoding="utf-8")
    if old not in value:
        raise SystemExit(name)
    path.write_text(value.replace(old, new, 1), encoding="utf-8")

changelog = root / "CHANGELOG.md"
value = changelog.read_text(encoding="utf-8")
entry = "\n### P2G: bootstrap cleanup boundaries\n\n- Классифицированы пять независимых shutdown cleanup boundaries.\n- Unresolved broad baseline уменьшен с 63 до 58.\n"
if entry.strip() not in value:
    value = value.replace("## [Unreleased]\n", "## [Unreleased]\n" + entry, 1)
changelog.write_text(value, encoding="utf-8")
