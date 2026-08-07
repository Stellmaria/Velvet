# Librarian reconcile host temp and full archive backfill

- Дата: 2026-08-08
- ID: librarian-reconcile-full-archive-20260808
- Линия/фаза: Arthur / Storage Librarian production hardening
- Статус: в работе
- Ветка: `fix/librarian-reconcile-tmp`
- Базовый commit: `c6f0544730aed289b4d105a01389d15c53b1e9f1`

## Перед началом

### Цель

1. убрать production failure штатного `reconcilectl submit librarian` при systemd `PrivateTmp=true`;
2. сохранить sandbox, а не отключать `PrivateTmp`;
3. добавить явный bounded режим полного архивного анализа через локальный Ollama;
4. не превращать full archive в массовый enqueue одной транзакцией.

### Production evidence

На production checkout `8e77885c676c51fbae49e513c28265e8a45b7e47` первый fixed reconcile завершился ошибкой:

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

### Причина

Это namespace boundary, а не повреждение context pack. Ослаблять unit до `PrivateTmp=false` не требуется.

## Планируемый контракт

### Reconcile temp

`host_reconcile_entrypoint.py` создаёт private mode `0700` temp directory внутри уже разрешённого host-visible reconcile state boundary и передаёт его дочерним process через `TMPDIR`.

`PrivateTmp=true` остаётся включённым.

### Full archive

Полный архив включается только отдельным explicit opt-in:

```dotenv
STORAGE_LIBRARIAN_AUTO_ENQUEUE=true
STORAGE_LIBRARIAN_AUTO_BACKFILL=true
STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID=0
```

Scheduler в этом режиме:

- использует обычный `StorageLibrarianRepository`;
- вызывает bounded `enqueue_pending(..., limit=batch_size)`;
- затем выполняет одну `process_once(auto_enqueue=false)` итерацию;
- по умолчанию batch `1`, interval `60` секунд;
- analysis client остаётся `OllamaStorageAnalysisClient`;
- cloud fallback для analysis не добавляется;
- encrypted/unsupported/oversized objects остаются исключены;
- текущий manual allowlist определяет поддерживаемые archive kinds;
- mode можно остановить `disable_afk.sh` без остановки Ollama и ручных команд.

New-only AFK остаётся отдельным режимом с `AUTO_BACKFILL=false` и ненулевым cutoff.

## Риски и ограничения

- Full archive может работать долго на CPU-only inference; это ожидаемо.
- Увеличение batch/concurrency ради скорости не является частью изменения.
- Успешные analysis reports могут постепенно заполнять Hermes Reports, если publication включена.
- Vision-only содержимое не становится поддержанным этим изменением; vision остаётся отдельной задачей.
- Full archive не обходит encryption, size и allowed-kind boundaries.
- Production deployment после merge должен сохранить source/image provenance; изменение env включается только после доставки соответствующего application image.

## Критерии готовности

- `PrivateTmp=true` остаётся в systemd unit;
- reconcile child process получает host-visible `TMPDIR`;
- regression test фиксирует этот boundary;
- new-only script явно сбрасывает archive backfill flag;
- full-archive script включает `AUTO_ENQUEUE=true` и `AUTO_BACKFILL=true`, требует local Ollama и batch=1 по умолчанию;
- scheduler при backfill использует `enqueue_pending`, а не mass enqueue;
- status различает `AFK new-only` и `AFK full-archive`;
- disable script выключает оба background режима;
- protected CI зелёный на exact PR head;
- merge выполняется только после зелёного CI.

## После завершения

Заполнить final PR/head/merge SHA и production rollout evidence после protected CI и merge.
