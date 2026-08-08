# Krita local server wake contract

- Дата: 2026-08-08
- ID: `2026-08-08-krita-local-server-wake`
- Линия/фаза: Watermark / Krita server runtime integration
- Статус: `частично`
- Ветка: `fix/krita-local-server-wake`
- Базовый commit: `c01c5d697200edc308061ed3744dfefd99808b60`

## Перед началом

### Цель

Убрать ложный вызов Supervisor `/v1/krita/ensure` в production local-server режиме, где Krita уже запущена отдельным постоянно работающим Docker worker и обрабатывает задания через общий runtime bridge.

### Исходный контекст

Production alert сообщал `Could not wake Krita for public archive watermark: Route not found.`. Проверка показала, что `velvet_bot.krita_supervisor.wake_krita()` вызывает `/v1/krita/ensure`, тогда как production `scripts/server_supervisor.py` не публикует маршруты `/v1/krita/*`. Одновременно server deploy contract закрепляет локальный режим как включённый watermark, выключенный remote worker и bridge внутри `/app/runtime/krita`; контейнер Krita в этом режиме уже работает постоянно и не требует wake через Supervisor.

### Планируемый объём

- распознавать только явный local-server Krita contract;
- в этом режиме завершать `wake_krita()` как успешный no-op до создания Supervisor client;
- сохранить прежнее Supervisor поведение для остальных окружений;
- добавить regression tests на server-local и non-server случаи;
- не менять server Supervisor API, Docker lifecycle или watermark job contract.

### Критерии готовности

- local server worker не вызывает Supervisor;
- отсутствие server bridge marker не отключает обычный Supervisor wake;
- существующие watermark presentation contracts проходят;
- server preflight и Krita deployment contracts не регрессируют;
- required GitHub CI зелёный перед merge.

### Риски и ограничения

Основной риск заключается в слишком широком определении local-server режима. Поэтому bridge path не получает server default внутри generic runtime helper: отсутствие `KRITA_BRIDGE_DIR` должно сохранять обычное Supervisor поведение. Этот fix не добавляет новые privileged server routes и не меняет lifecycle отдельного Krita container.

## После завершения

### Фактически сделано

В `velvet_bot/krita_supervisor.py` добавлена проверка явного local-server contract: watermark включён, remote worker выключен, а `KRITA_BRIDGE_DIR` указывает на `/app/runtime/krita` или вложенный путь. Для этого режима `wake_krita()` возвращает успех без построения Supervisor client. Для остальных конфигураций прежний `/v1/krita/ensure` flow сохранён. В `tests/test_watermark_presentation_contracts.py` добавлены regression tests для обоих путей.

### Миграции и совместимость

Миграции БД и конфигурации не требуются. Production server env уже задаёт нужный bridge path. Windows и другие non-server конфигурации сохраняют прежнее поведение, если server bridge marker отсутствует.

### Проверки

Локально на production host в контейнерном Python 3.13 пройдены syntax compile и 25 targeted unittest cases. Отдельно пройдены 9 Krita server deployment contract functions. `git diff --check` чистый. PR CI выявил только обязательное отсутствие отдельной worklog-записи; этот файл добавлен для выполнения project notes contract. Финальный required CI должен пройти на новом exact head.

### PR и commit

PR: `#735 Skip Krita wake for local server worker`.

Ветка: `fix/krita-local-server-wake`. Head commit после добавления worklog определяется GitHub. Merge SHA фиксируется после required green CI и merge.

### Незавершённое

- дождаться повторного required CI на head с worklog;
- подтвердить `behind_by=0` непосредственно перед merge;
- слить только exact green head;
- production deploy выполняется отдельным operational шагом после merge.

### Следующий шаг

Дождаться зелёного required CI для PR #735, перевести PR из draft в ready и выполнить merge с expected head SHA при актуальном `main`.
