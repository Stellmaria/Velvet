# Сессия: Krita headless server bridge stabilization

- Дата: `2026-08-08`
- ID: `krita-headless-server-bridge-20260808`
- Линия/фаза: `Velvet / Krita / production server hotfix`
- Статус: `готово к CI`
- Ветка: `fix/krita-headless-bridge`
- Базовый commit: `8b160db820592c36f51da491b0525754f6954bdf`

## Перед началом

### Цель

Стабилизировать локальный Linux server worker Krita для watermark bridge и привести deployment-контракт в соответствие с уже поддерживаемым режимом `KRITA_WATERMARK_ENABLED=true` + `KRITA_REMOTE_WORKER_ENABLED=false`.

### Исходный контекст

Installer корректно переводил production env в локальный server mode и задавал `KRITA_BRIDGE_DIR=/app/runtime/krita`, однако `scripts/server_preflight.py` всё ещё безусловно запрещал `KRITA_WATERMARK_ENABLED=true`, поэтому `velvet-krita.service` завершался на `ExecStartPre` до запуска worker.

После ручного запуска Compose Krita успешно собиралась и проходила healthcheck. Host-side `krita-smoke.sh` при запуске от пользователя `velvet` не мог записать source PNG в bridge-каталог, созданный для container UID/GID `10001:10001`; запуск smoke через sudo обходил права, но выявил более серьёзный runtime defect.

Каждый реальный bridge request успевал записать успешный response и PNG, после чего Krita завершалась с `SAFE ASSERT (krita): "!sanityCheckPointer.isValid()" in ./libs/ui/KisDocument.cpp, line 698` и `Segmentation fault`. Docker restart policy маскировал дефект: один smoke соответствовал одному restart. OOM был исключён.

Отдельные тесты с QtQuick/QML runtime и `waitForDone()` перед `Document.close()` не устранили crash. Стабильность появилась только после перевода server request lifecycle в действительно headless режим: bridge перестал создавать GUI `View`, document jobs ожидаются после открытия и перед закрытием, а `setActiveNode()` выполняется только для реального active GUI document.

### Планируемый объём

- убрать `window.addView(document)` из server bridge request lifecycle;
- ожидать Krita document jobs после `openDocument()` и перед `close()`;
- не выполнять GUI-only `setActiveNode()` для headless bridge document;
- добавить QtQuick Controls runtime в server image;
- разрешить и валидировать локальный Krita server mode в preflight;
- выполнять smoke внутри уже запущенного Krita container под его UID вместо host-side записи в bridge;
- считать restart/recreate Krita во время smoke ошибкой, даже если PNG уже был успешно записан;
- закрепить поведение regression-contract tests.

### Критерии готовности

- protected CI зелёный на exact PR head;
- local Krita server mode проходит preflight, а bridge path вне `/app/runtime/krita` отклоняется;
- smoke не требует host write access к bridge-каталогам;
- smoke фиксирует restart/recreate worker как failure;
- server bridge contract запрещает возвращение `window.addView(document)`;
- Docker image содержит необходимый QtQuick runtime.

### Риски и ограничения

Дополнительный QML package увеличивает server image, но не расширяет network/runtime privileges. Smoke по-прежнему проверяет один реальный builtin-logo request, поэтому не заменяет более широкую функциональную проверку пользовательских PNG/SVG assets. Live validation на production-like VPS остаётся обязательным доказательством runtime stability, потому что статический контракт не способен воспроизвести внутренний lifecycle Krita.

## После завершения

### Фактически сделано

- `tools/krita/velvet_logo/velvet_logo.py`: server bridge больше не создаёт GUI view; добавлены lifecycle waits; `setActiveNode()` ограничен active GUI document;
- `Dockerfile.krita-server`: добавлен `qml-module-qtquick-controls`;
- `scripts/server_preflight.py`: удалён устаревший unconditional ban на `KRITA_WATERMARK_ENABLED=true`; local mode валидирует bridge root; remote mode требует включённый watermark feature;
- `deploy/server/krita-smoke.sh`: request теперь создаётся и проверяется внутри Krita container; host bridge permissions больше не требуются; после ответа проверяются container identity и `RestartCount`;
- `tests/test_server_preflight.py`: добавлены positive/negative contracts для local Krita mode и remote dependency;
- `tests/test_krita_server_deployment_contract.py`: добавлены headless lifecycle, QML runtime и restart-aware smoke contracts.

### Миграции и совместимость

Миграций базы данных и данных нет. Production env schema не меняется. Fail-closed default `KRITA_WATERMARK_ENABLED=false` в example-конфигурации сохраняется; installer по-прежнему явно включает local server mode. Remote worker security validation сохраняет token и loopback/public-bind guardrails.

### Проверки

До переноса фикса в repository на VPS дефект воспроизводился детерминированно: каждый успешный smoke request приводил к одному segfault/restart.

Тестовый headless image с тем же lifecycle patch прошёл 10 последовательных реальных bridge smoke jobs со следующими итогами:

- `restarts=0`;
- `status=running`;
- `exit=0`;
- `oom=false`;
- `health=healthy`;
- в логах отсутствовали `SAFE ASSERT`, `Segmentation fault`, `Timer is not a type` и `Type Button unavailable`.

На первоначальном PR head `type check` завершился успешно. `project notes contract` завершился failure только из-за отсутствия отдельной worklog-записи; этот файл добавлен для нового exact head, после чего protected CI должен пройти повторно.

### PR и commit

PR: `#717 Fix headless Krita bridge on Linux server`.

Merge разрешён только после terminal green protected CI на exact head. Нельзя считать успешный PNG достаточным smoke evidence без проверки отсутствия container restart.

### Следующий шаг

Дождаться terminal green CI для PR #717 и слить exact reviewed head в `main`. После merge production VPS должен перейти с временного test image на canonical `velvet-krita-server:local` через штатный server deployment/install flow; затем требуется health + restart-aware smoke подтверждение уже из `main`.

### Незавершённое

- protected CI на head с этой worklog-записью;
- merge PR #717 в `main`;
- production redeploy canonical Krita image;
- финальный live smoke после redeploy.
