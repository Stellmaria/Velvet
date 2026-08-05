# Сессия

- Дата: `2026-08-05`
- ID: `hermes-orchestration-installer-mode-20260805`
- Статус: `завершено`
- Ветка: `fix/hermes-orchestration-installer-mode`
- Базовый commit: `74bfb3a19506e5b2a387f4de62b711808ea88a4c`
- Линия/фаза: `production recovery / Hermes orchestration install`

## Перед началом

### Цель

Устранить подтверждённый production-отказ orchestration installer, который не мог запустить канонический Hermes coder installer из-за отсутствующего executable mode.

### Исходный контекст

После server deploy commit `23439a95f13115e3339db632a502e7b9205f49b5` команда `sudo -H bash deploy/hermes-orchestration/install.sh` подготовила credentials, затем завершилась ошибкой `Permission denied` на `/srv/velvet/deploy/hermes-coders/install.sh`. Orchestration вызывает этот файл напрямую, однако Git tree хранит его с mode `100644`.

Из-за раннего выхода не были выполнены canonical coder reconcile, установка актуального AppArmor profile, systemd reconciliation и запуск coder router. Последующие ручные рестарты повторно использовали старую failed-конфигурацию.

### Планируемые изменения

- установить executable mode для `deploy/hermes-coders/install.sh` в Git tree;
- добавить regression contract, который проверяет owner execute bit и прямой orchestration call;
- открыть отдельный PR и слить только после обязательного CI.

### Вне объёма

- изменение логики вложенного installer;
- изменение Codex rate-limit DTO или Telegram-формата;
- production rollout до merge;
- диагностика отдельного Telegram Storage incident `#449`.

### Критерии готовности

- Git хранит `deploy/hermes-coders/install.sh` как executable;
- checkout с обычным `umask 022` получает исполняемый файл;
- orchestration сохраняет единственный canonical вызов installer;
- обязательные CI-проверки проходят.

### Риски и допущения

- production checkout ещё находится на более старом commit и требует controlled update;
- перед rollout необходимо восстановить ownership checkout после прежнего root-run deploy;
- installer остаётся root-only и идемпотентным по существующему контракту.

## После завершения

### Что сделано

- mode канонического Hermes coder installer изменён с `100644` на `100755` без изменения содержимого;
- добавлен contract test для executable bit и orchestration invocation;
- изменение ограничено deployment metadata, тестом и этой записью.

### Что проверено

- подтверждён фактический Git mode `100644` на baseline;
- подтверждён прямой вызов `"$CODERS_SOURCE/install.sh"` в orchestration installer;
- required CI запускается на PR.

### Что осталось

- дождаться required CI;
- слить PR;
- выполнить one-time ownership repair production checkout;
- обновить checkout controlled deploy от пользователя `velvet`;
- повторно запустить orchestration installer и проверить Codex Plus limits;
- отдельно извлечь traceback и DB details incident `#449`.

### Решения и компромиссы

Executable mode соответствует фактическому контракту прямого вызова и сохраняет shebang как canonical interpreter. Логика installer не дублируется и не оборачивается дополнительным shell-слоем.

### Важные детали для следующей сессии

Production server на момент дефекта находился на `23439a95f13115e3339db632a502e7b9205f49b5`. `main` уже содержит PR `#636`, запрещающий будущие server deploy от root и выполняющий reset под `umask 022`. Первый rollout после этого дефекта должен восстановить ownership только Git checkout metadata и tracked paths, не трогая PostgreSQL data volumes.

### PR и commit

- PR: создаётся после публикации ветки;
- merge commit: фиксируется после зелёного CI.
