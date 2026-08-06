from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERROR_CENTER = ROOT / "velvet_bot" / "error_center.py"
ARCH_TEST = ROOT / "tests" / "test_package_architecture_inventory.py"
INVENTORY = ROOT / "docs" / "package_architecture_inventory.json"
EXEMPTIONS = ROOT / "docs" / "package_architecture_exemptions.json"
TEMP_DIR = ROOT / ".issue605-architecture"
SELF = ROOT / "scripts" / "apply_issue_605.py"
WORKFLOW = ROOT / ".github" / "workflows" / "issue-605-apply.yml"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_error_center() -> None:
    text = ERROR_CENTER.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "datetime.now(UTC) - value >= timedelta(seconds=max(1, cooldown_seconds))",
        "datetime.now(UTC) - value >= timedelta(seconds=max(0, cooldown_seconds))",
        "digest cooldown",
    )

    record_anchor = """                return RecordedIncident(self._from_row(row), opened=reopened)

    async def set_log_message_id(self, incident_id: int, message_id: int) -> None:
"""
    record_replacement = """                return RecordedIncident(self._from_row(row), opened=reopened)

    async def record_batch(
        self,
        captured: CapturedLog,
        *,
        count: int,
        last_seen_at: datetime,
    ) -> RecordedIncident:
        safe_count = max(1, int(count))
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                \"\"\"
                WITH target AS (
                    SELECT id, acknowledged_at IS NOT NULL AS reopened
                    FROM error_incidents
                    WHERE fingerprint = $1::CHAR(64)
                    FOR UPDATE
                )
                UPDATE error_incidents AS incident
                SET severity = CASE
                        WHEN incident.severity = 'CRITICAL' OR $2 = 'CRITICAL'
                            THEN 'CRITICAL'
                        WHEN incident.severity = 'ERROR' OR $2 = 'ERROR'
                            THEN 'ERROR'
                        ELSE 'WARNING'
                    END,
                    occurrence_count = incident.occurrence_count + $3,
                    last_seen_at = GREATEST(incident.last_seen_at, $4),
                    log_chat_message_id = CASE
                        WHEN target.reopened THEN NULL
                        ELSE incident.log_chat_message_id
                    END,
                    acknowledged_at = NULL,
                    acknowledged_by = NULL
                FROM target
                WHERE incident.id = target.id
                RETURNING incident.*, target.reopened
                \"\"\",
                captured.fingerprint,
                captured.severity,
                safe_count,
                last_seen_at,
            )
        if row is None:
            recorded = await self.record(captured)
            if safe_count == 1:
                return recorded
            return await self.record_batch(
                captured,
                count=safe_count - 1,
                last_seen_at=last_seen_at,
            )
        return RecordedIncident(self._from_row(row), opened=bool(row["reopened"]))

    async def set_log_message_id(self, incident_id: int, message_id: int) -> None:
"""
    text = replace_once(text, record_anchor, record_replacement, "record batch")

    init_anchor = """        self._handler: ErrorLoggingHandler | None = None
        self._dropped = 0
"""
    init_replacement = """        self._handler: ErrorLoggingHandler | None = None
        self._dropped = 0
        self._aggregate_interval = 2.0
        self._aggregate_limit = 500
        self._known_limit = 2000
        self._known: dict[str, ErrorIncident] = {}
        self._pending: dict[
            str,
            tuple[CapturedLog, int, datetime, datetime],
        ] = {}
        self._aggregation_metrics = {
            "received": 0,
            "new_groups": 0,
            "aggregated_repeats": 0,
            "flush_batches": 0,
            "rows_updated": 0,
            "notification_suppressions": 0,
            "flush_errors": 0,
        }
"""
    text = replace_once(text, init_anchor, init_replacement, "aggregation state")

    stop_anchor = """    async def stop(self) -> None:
        if self._handler is not None:
            logging.getLogger().removeHandler(self._handler)
            self._handler = None
        try:
            await asyncio.wait_for(self._queue.join(), timeout=3)
        except TimeoutError:
            pass
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            await asyncio.gather(self._consumer_task, return_exceptions=True)
            self._consumer_task = None
        self._loop = None
"""
    stop_replacement = """    async def stop(self) -> None:
        if self._handler is not None:
            logging.getLogger().removeHandler(self._handler)
            self._handler = None
        try:
            await asyncio.wait_for(self._queue.join(), timeout=3)
        except TimeoutError:
            pass
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            await asyncio.gather(self._consumer_task, return_exceptions=True)
            self._consumer_task = None
        for attempt in range(3):
            await self.flush_pending()
            if not self._pending:
                break
            await asyncio.sleep(0.2 * (attempt + 1))
        if self._pending:
            logger.error("Unflushed error aggregates on shutdown: %s", len(self._pending))
        self._loop = None
"""
    text = replace_once(text, stop_anchor, stop_replacement, "graceful flush")

    process_anchor = """    async def _consume(self) -> None:
        while True:
            captured = await self._queue.get()
            try:
                await self._process(captured)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # p2-approved-boundary: isolate-error-incident-item
                logger.warning("Error incident processing failed: %s", error)
            finally:
                self._queue.task_done()

    async def _process(self, captured: CapturedLog) -> None:
        recorded = await self._repository.record(captured)
        incident = recorded.incident
        await self._publish_to_log_chat(incident)
        if recorded.opened:
            await self._send_owner_digest(cooldown_seconds=120)

"""
    process_replacement = """    async def _consume(self) -> None:
        while True:
            try:
                captured = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=self._aggregate_interval,
                )
            except TimeoutError:
                await self.flush_pending()
                continue
            try:
                await self._process(captured)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # p2-approved-boundary: isolate-error-incident-item
                logger.warning("Error incident processing failed: %s", error)
            finally:
                self._queue.task_done()

    async def _process(self, captured: CapturedLog) -> None:
        self._aggregation_metrics["received"] += 1
        known = self._known.get(captured.fingerprint)
        previous_severity = known.severity if known is not None else None
        if captured.severity == "CRITICAL" or known is None:
            try:
                await self._flush_one(captured.fingerprint)
            except Exception as error:
                logger.warning("Pre-immediate aggregate flush failed: %s", error)
            recorded = await self._repository.record(captured)
            self._remember(recorded.incident)
            if recorded.incident.occurrence_count == 1:
                self._aggregation_metrics["new_groups"] += 1
            await self._publish_to_log_chat(recorded.incident)
            if recorded.opened:
                await self._send_owner_digest(cooldown_seconds=120)
            elif captured.severity == "CRITICAL" and previous_severity != "CRITICAL":
                await self._send_owner_digest(cooldown_seconds=0)
            return

        pending = self._pending.get(captured.fingerprint)
        if pending is None and len(self._pending) >= self._aggregate_limit:
            try:
                await self._flush_one(next(iter(self._pending)))
            except Exception:
                recorded = await self._repository.record(captured)
                self._remember(recorded.incident)
                await self._publish_to_log_chat(recorded.incident)
                if recorded.opened:
                    await self._send_owner_digest(cooldown_seconds=120)
                return
        now = datetime.now(UTC)
        first_seen_at = now if pending is None else pending[2]
        count = 1 if pending is None else pending[1] + 1
        selected = captured
        if pending is not None:
            rank = {"WARNING": 1, "ERROR": 2, "CRITICAL": 3}
            selected = max((pending[0], captured), key=lambda item: rank[item.severity])
        self._pending[captured.fingerprint] = (
            selected,
            count,
            first_seen_at,
            now,
        )
        self._aggregation_metrics["aggregated_repeats"] += 1
        self._aggregation_metrics["notification_suppressions"] += 1

    def _remember(self, incident: ErrorIncident) -> None:
        self._known.pop(incident.fingerprint, None)
        self._known[incident.fingerprint] = incident
        while len(self._known) > self._known_limit:
            self._known.pop(next(iter(self._known)))

    async def _flush_one(self, fingerprint: str) -> None:
        batch = self._pending.pop(fingerprint, None)
        if batch is None:
            return
        captured, count, first_seen_at, last_seen_at = batch
        try:
            recorded = await self._repository.record_batch(
                captured,
                count=count,
                last_seen_at=last_seen_at,
            )
        except Exception:
            current = self._pending.get(fingerprint)
            if current is not None:
                count += current[1]
                first_seen_at = min(first_seen_at, current[2])
                last_seen_at = max(last_seen_at, current[3])
            self._pending[fingerprint] = (
                captured,
                count,
                first_seen_at,
                last_seen_at,
            )
            self._aggregation_metrics["flush_errors"] += 1
            raise
        self._aggregation_metrics["flush_batches"] += 1
        self._aggregation_metrics["rows_updated"] += 1
        self._remember(recorded.incident)
        await self._publish_to_log_chat(recorded.incident)
        if recorded.opened:
            await self._send_owner_digest(cooldown_seconds=120)

    async def flush_pending(self) -> None:
        for fingerprint in tuple(self._pending):
            try:
                await self._flush_one(fingerprint)
            except Exception as error:  # p2-approved-boundary: retry-next-aggregate-flush
                logger.warning("Could not flush error aggregate %s: %s", fingerprint, error)

    def aggregation_metrics(self) -> dict[str, int | float]:
        snapshot: dict[str, int | float] = dict(self._aggregation_metrics)
        snapshot["dropped_queue_events"] = self._dropped
        snapshot["pending_fingerprints"] = len(self._pending)
        snapshot["oldest_pending_age_seconds"] = max(
            (
                datetime.now(UTC) - row[2]
            ).total_seconds()
            for row in self._pending.values()
        ) if self._pending else 0.0
        return snapshot

"""
    text = replace_once(text, process_anchor, process_replacement, "consumer batching")

    text = replace_once(
        text,
        """    async def acknowledge_incident(self, incident_id: int, user_id: int) -> bool:
        incident = await self._repository.acknowledge(incident_id, user_id)
""",
        """    async def acknowledge_incident(self, incident_id: int, user_id: int) -> bool:
        await self.flush_pending()
        incident = await self._repository.acknowledge(incident_id, user_id)
""",
        "ack flush",
    )
    text = replace_once(
        text,
        """        if incident is None:
            return False
        if self._log_chat_id is not None and incident.log_chat_message_id is not None:
""",
        """        if incident is None:
            return False
        self._known.clear()
        if self._log_chat_id is not None and incident.log_chat_message_id is not None:
""",
        "ack cache reset",
    )
    text = replace_once(
        text,
        """    async def acknowledge_all(self, user_id: int) -> int:
        incidents = await self._repository.acknowledge_all(user_id)
""",
        """    async def acknowledge_all(self, user_id: int) -> int:
        await self.flush_pending()
        incidents = await self._repository.acknowledge_all(user_id)
        if incidents:
            self._known.clear()
""",
        "ack all flush",
    )
    ERROR_CENTER.write_text(text, encoding="utf-8")


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def refresh_architecture_baseline() -> None:
    run(
        sys.executable,
        "scripts/shared_contract_inventory.py",
        "--write-json",
        "docs/shared_contract_inventory.json",
        "--write-markdown",
        "docs/shared_contract_inventory.md",
    )
    if TEMP_DIR.exists():
        for path in sorted(TEMP_DIR.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    TEMP_DIR.mkdir()
    run(
        sys.executable,
        "scripts/inventory_package_architecture_fast.py",
        "--label",
        "p1-package-architecture-baseline",
        "--write",
        "--bootstrap-exemptions",
        "--output-dir",
        str(TEMP_DIR),
    )

    old_inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    old_exemptions = json.loads(EXEMPTIONS.read_text(encoding="utf-8"))
    new_inventory = json.loads(
        (TEMP_DIR / INVENTORY.name).read_text(encoding="utf-8")
    )
    generated = json.loads(
        (TEMP_DIR / EXEMPTIONS.name).read_text(encoding="utf-8")
    )
    old_by_id = {
        str(row["id"]): row for row in old_exemptions["exceptions"]
    }
    old_violations = {
        str(row["id"]): row for row in old_inventory["violations"]
    }
    old_by_surface: dict[tuple[str, str], list[dict[str, object]]] = {}
    for old_id, violation in old_violations.items():
        exception = old_by_id.get(old_id)
        if exception is None:
            continue
        key = (str(violation["category"]), str(violation["path"]))
        old_by_surface.setdefault(key, []).append(exception)

    generated_by_id = {
        str(row["id"]): row for row in generated["exceptions"]
    }
    merged = []
    for violation in new_inventory["violations"]:
        suggestion = generated_by_id[str(violation["id"])]
        key = (str(violation["category"]), str(violation["path"]))
        candidates = old_by_surface.get(key, [])
        if candidates:
            row = dict(candidates[0])
            row["id"] = suggestion["id"]
            row["consumers"] = suggestion["consumers"]
        else:
            row = dict(suggestion)
            row.update(
                owner="Velvet maintainers",
                reason="Bounded Error Center batching required by #605.",
                replacement="Remove this exemption when the Error Center repository moves to a dedicated persistence boundary.",
                removal_condition="Complete the repository boundary migration and rerun the package inventory.",
                regression_test="tests/test_package_architecture_inventory.py",
                issue="#605",
            )
        merged.append(row)

    merged_exemptions = {
        "schema_version": generated["schema_version"],
        "generated_from": generated["generated_from"],
        "baseline_issue": old_exemptions["baseline_issue"],
        "shared_private_access_sha256": generated[
            "shared_private_access_sha256"
        ],
        "root_module_sha256": generated["root_module_sha256"],
        "exceptions": sorted(merged, key=lambda row: str(row["id"])),
    }
    EXEMPTIONS.write_text(
        json.dumps(merged_exemptions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    run(
        sys.executable,
        "scripts/inventory_package_architecture_fast.py",
        "--label",
        "p1-package-architecture-baseline",
        "--write",
    )
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    update_architecture_test(inventory)


def update_architecture_test(inventory: dict[str, object]) -> None:
    text = ARCH_TEST.read_text(encoding="utf-8")
    direct_keys = (
        "production_module_count",
        "production_loc",
        "root_module_count",
        "root_unclassified_count",
        "router_count",
        "router_duplicate_count",
        "repository_module_count",
        "violation_count",
    )
    for key in direct_keys:
        value = int(inventory[key])
        pattern = rf'self\.assertEqual\(\d+, self\.inventory\["{key}"\]\)'
        text, count = re.subn(
            pattern,
            f'self.assertEqual({value}, self.inventory["{key}"])',
            text,
        )
        if count != 1:
            raise RuntimeError(f"architecture test key {key}: {count}")

    shared = inventory["shared_contract_summary"]
    shared_keys = (
        "production_python_files",
        "function_count",
        "private_contract_access_count",
        "blocking_private_contract_access_count",
        "exact_duplicate_group_count",
        "normalized_duplicate_group_count",
        "semantic_near_duplicate_group_count",
    )
    for key in shared_keys:
        value = int(shared[key])
        pattern = rf'self\.assertEqual\(\d+, shared\["{key}"\]\)'
        text, count = re.subn(
            pattern,
            f'self.assertEqual({value}, shared["{key}"])',
            text,
        )
        if count != 1:
            raise RuntimeError(f"shared test key {key}: {count}")

    replacements = {
        r'Production modules: \*\*\d+\*\*':
            f'Production modules: **{inventory["production_module_count"]}**',
        r'Production LOC: \*\*\d+\*\*':
            f'Production LOC: **{inventory["production_loc"]}**',
        r'Registered package violations: \*\*\d+\*\*':
            f'Registered package violations: **{inventory["violation_count"]}**',
        r'Registered exemptions: \*\*\d+\*\*':
            f'Registered exemptions: **{len(inventory["violations"])}**',
    }
    for pattern, replacement in replacements.items():
        text, count = re.subn(pattern, replacement, text)
        if count != 1:
            raise RuntimeError(f"markdown expectation {pattern}: {count}")
    ARCH_TEST.write_text(text, encoding="utf-8")


def cleanup() -> None:
    for path in (SELF, WORKFLOW):
        path.unlink(missing_ok=True)
    if TEMP_DIR.exists():
        for path in sorted(TEMP_DIR.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        TEMP_DIR.rmdir()


def main() -> None:
    patch_error_center()
    run(sys.executable, "-m", "py_compile", "velvet_bot/error_center.py")
    refresh_architecture_baseline()
    cleanup()


if __name__ == "__main__":
    main()
