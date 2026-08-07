# Librarian reconcile host temp and full archive backfill

- Дата: 2026-08-08
- ID: librarian-reconcile-full-archive-20260808
- Линия/фаза: Arthur / Storage Librarian production hardening
- Статус: `частично`
- Ветка: `fix/librarian-reconcile-tmp`
- Базовый commit: `c6f0544730aed289b4d105a01389d15c53b1e9f1`

## Перед началом

### Цель

1. убрать production failure штатного `reconcilectl submit librarian` при systemd `PrivateTmp=true`;
2. сохранить sandbox, а не отключать `PrivateTmp`;
3. добавить явный bounded режим полного архивного анализа через локальный Ollama;
4. не превращать full archive в массовый enqueue одной транзакцией.

### Исходный контекст

На production checkout `8e77885c676c51fbae49e513c28265e8a45b7e47` fixed reconcile завершился ошибкой:

```text
Velvet Librarian profile preparation failed: Отсутствует SOUL.md, AGENTS.md или context-manifest.json Velvet Librarian.
```

До ошибки Brain Vault validation и compile проходили успешно. `hermes-operator-reconcile.service` использует `PrivateTmp=true`, а Librarian installer создавал context pack через `mktemp -d` и передавал полученный path Docker daemon как bind source. Путь private `/tmp` существовал только в mount namespace systemd service, поэтому host Docker daemon не видел compiled files.

Контрольный production workaround с `TMPDIR=/srv/hermes-operator-control/reconcile-tmp` прошёл полностью:

- Brain Vault validation/compile: OK;
- local-only deny-all profile contract: OK;
- Bot-to-Hermes health: OK;
- Bot-to-Ollama structured analysis smoke: OK;
- Arthur, storage gateway, Librarian Hermes и Ollama: healthy;
- `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`;
- configured `MAX_TEXT_CHARS=120000`, effective `11520`;
- context `8192`, output `384`, heartbeat present;
- ручной Telegram acceptance Arthur: успешно.

Пользователь после успешной ручной acceptance явно запросил полный архивный анализ через локальный Ollama и включение фонового режима. Существующий `enable_afk.sh` намеренно работал только `new-only`, фиксируя текущий максимальный Storage ID как cutoff, поэтому этот режим нельзя было использовать как скрытый full backfill.

### Планируемый объём

- Оставить `PrivateTmp=true` в systemd unit.
- Создавать host-visible reconcile temp внутри уже разрешённого `/srv/hermes-operator-control/reconcile-state` и передавать его дочерним installer-процессам через `TMPDIR`.
- Сохранить AFK `new-only` как отдельный fail-closed режим с ненулевым cutoff.
- Добавить отдельный opt-in full-archive режим с `AUTO_BACKFILL=true` и `AUTO_MIN_OBJECT_ID=0`.
- Использовать существующий `StorageLibrarianRepository.enqueue_pending(..., limit=batch_size)` вместо массового enqueue всего архива.
- По умолчанию обрабатывать один объект за цикл через `OllamaStorageAnalysisClient` и локальный `http://ollama-librarian:11434`.
- Сохранить encryption, size, kind и unsupported-content ограничения.
- Оставить Arthur container без второго фонового scheduler; background mode живёт в основном Velvet bot process.
- Обновить operator scripts, status text, env example, runbook и regression tests.

### Критерии готовности

- `PrivateTmp=true` остаётся в systemd unit.
- Reconcile child process получает host-visible `TMPDIR` внутри reconcile-state boundary.
- Regression test фиксирует PrivateTmp/Docker bind boundary.
- New-only script явно устанавливает `STORAGE_LIBRARIAN_AUTO_BACKFILL=false`.
- Full-archive script включает `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true`, `STORAGE_LIBRARIAN_AUTO_BACKFILL=true`, `STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID=0`, требует local Ollama и batch `1` по умолчанию.
- Scheduler при backfill использует bounded `enqueue_pending`, а не mass enqueue.
- `/storage_librarian` различает `AFK new-only` и `AFK full-archive`.
- Disable script выключает оба background режима.
- Protected CI зелёный на exact integrated PR head.
- Merge выполняется без обхода branch protection.

### Риски и ограничения

- Full archive может работать долго на CPU-only inference; это ожидаемо.
- Увеличение batch/concurrency ради скорости не входит в изменение.
- Успешные analysis reports могут постепенно заполнять Hermes Reports, если publication включена.
- Vision-only содержимое не становится поддержанным этим изменением; vision остаётся отдельной задачей.
- Full archive не обходит encryption, size, allowed-kind и unsupported-content boundaries.
- Production env нельзя переключать в full-backfill до доставки application image, содержащего новый scheduler contract.
- Repo merge сам по себе не является production deployment; rollout и включение backfill требуют отдельной проверки source/image provenance.

## После завершения

### Фактически сделано

- `deploy/hermes-reconcile/host_reconcile_entrypoint.py` создаёт `reconcile-state/tmp` с mode `0700` и передаёт этот host-visible path как `TMPDIR` фиксированным дочерним reconcile-командам.
- Systemd sandbox не ослаблен: `PrivateTmp=true` сохранён.
- `deploy/hermes-librarian/enable_afk.sh` теперь явно оставляет `AUTO_BACKFILL=false` и сохраняет new-only cutoff contract.
- Добавлен `deploy/hermes-librarian/enable_full_archive.sh` с local-Ollama gate, `AUTO_ENQUEUE=true`, `AUTO_BACKFILL=true`, min object `0`, batch `1` и interval `60` секунд по умолчанию.
- `disable_afk.sh` выключает и enqueue, и backfill flags.
- Main bot scheduler различает new-only и full-archive; full mode использует bounded `enqueue_pending(..., limit=batch_size)` и затем одну `process_once(auto_enqueue=false)` итерацию.
- Status показывает активный full-archive режим, локальный Ollama, batch и interval.
- Arthur compose не получает второй scheduler; его hardcoded `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` не изменён.
- Обновлены env example, runbook и regression contracts.

### Миграции и совместимость

SQL migrations отсутствуют. Существующие analysis rows и Telegram Storage schema не меняются. Новый `STORAGE_LIBRARIAN_AUTO_BACKFILL` является opt-in env flag с безопасным default `false`.

Старый new-only режим остаётся совместимым: `AUTO_BACKFILL=false` требует ненулевой cutoff. Нулевой cutoff разрешён только при явном `AUTO_BACKFILL=true`.

Production `.env.server` с legacy `STORAGE_LIBRARIAN_MAX_TEXT_CHARS=120000` остаётся допустимым; effective runtime limit продолжает clamp до `11520` для standard context/output settings.

### Проверки

- Production workaround с host-visible `TMPDIR` уже подтвердил фактическую причину и успешный Librarian install.
- Manual Arthur Telegram acceptance на production прошла до repo fix.
- `tests/test_hermes_reconcile_checkout_entrypoint.py` проверяет host-visible TMPDIR при сохранённом `PrivateTmp=true`.
- `tests/test_storage_librarian_afk.py` проверяет явное разделение new-only/full-archive, local Ollama gate, bounded batch и disable contract.
- `type check` на integrated head `3490c46b1c73a1e40a61caccc83b9700cf10583f` завершился успешно.
- Остальные protected checks должны завершиться на следующем exact head после исправления worklog contract.

### PR и commit

- PR: `#714` — `Fix Librarian reconcile temp and add bounded full archive`.
- Ветка: `fix/librarian-reconcile-tmp`.
- Integrated merge-with-main head до worklog fix: `3490c46b1c73a1e40a61caccc83b9700cf10583f`.
- Финальный PR head и squash merge commit будут зафиксированы GitHub после terminal success protected CI.

### Незавершённое

- Protected CI ещё не завершён на финальном head.
- PR ещё не merged.
- Production ещё не получил новый scheduler code.
- `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true` и `STORAGE_LIBRARIAN_AUTO_BACKFILL=true` ещё не должны включаться на production до доставки нового application runtime.

### Следующий шаг

Дождаться terminal success всех required checks на exact PR head, при необходимости синхронизировать ветку с актуальным `main`, выполнить squash merge #714 без обхода branch protection, затем штатно обновить production application и включить `sudo bash deploy/hermes-librarian/enable_full_archive.sh` с последующей проверкой local Ollama route, batch `1`, queue progress и health Arthur/Librarian services.
