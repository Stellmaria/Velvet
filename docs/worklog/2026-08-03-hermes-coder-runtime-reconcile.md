# Сессия: закрепление production runtime Hermes coder

- Дата: 2026-08-03
- ID: 2026-08-03-hermes-coder-runtime-reconcile
- Линия/фаза: server operations / Hermes coder runtime
- Статус: завершено
- Ветка: fix/hermes-coder-runtime-reconcile
- Базовый commit: 3745713ffcab1ef3561bfdfed28ab7b6bf87a2f8

## Перед началом

### Цель

Перенести в репозиторий исправления, которые потребовались при live-развёртывании Codex runners для Velvet и Max, чтобы чистый deploy не зависел от ручного Compose override и исправления Git workspaces на сервере.

### Исходный контекст

Live smoke выявил три независимых дефекта:

- Codex containers наследовали `/init` и `main-wrapper.sh` базового Hermes image, но запускались как UID/GID `10000:10000`; `s6-overlay` завершался с кодом `100`, не имея прав исправить `/run`;
- runtime smoke выполнял Git probe внутри chat gateways от root и не видел `/opt/data/.gitconfig`, поэтому Git отвергал `/workspace` как `dubious ownership`;
- Max workspaces сохраняли SSH origin, тогда как изолированный GitHub contract и smoke требуют HTTPS и fine-grained `GH_TOKEN`.

Дополнительно повторный installer не гарантировал исправление владельцев уже существующих workspaces.

### Планируемый объём

- добавить tracked Compose runtime override;
- запускать Codex runner напрямую через Python entrypoint;
- явно передавать chat gateways `GIT_CONFIG_GLOBAL`;
- перед стартом нормализовать владельцев четырёх fixed workspaces;
- нормализовать fixed Git origins на HTTPS;
- подключить reconcile и override к systemd lifecycle;
- добавить regression-тесты для production failure modes.

### Критерии готовности

- Codex services не используют inherited `/init`;
- chat Git probe читает `/opt/data/.gitconfig`;
- Velvet и Max chat/Codex workspaces имеют UID/GID `10000:10000`;
- все четыре origin имеют фиксированные HTTPS URLs;
- systemd не объявляет runtime успешным до `runtime_smoke.py`;
- regression-тесты фиксируют runtime contract.

### Риски и ограничения

- recursive ownership repair может занять заметное время на первом запуске после старой установки;
- reconcile намеренно работает только с четырьмя фиксированными workspace paths и не принимает произвольные репозитории;
- production после merge должен перейти с временного `/srv/hermes-coders/runtime/compose.codex-entrypoint.yaml` на repository-managed `compose.runtime.yaml`.

## После завершения

### Фактически сделано

- добавлен `deploy/hermes-coders/compose.runtime.yaml`;
- chat gateways получают `GIT_CONFIG_GLOBAL=/opt/data/.gitconfig`;
- Codex runners получают прямой `python /app/codex_routed_runner.py` entrypoint и пустой command;
- добавлен `reconcile_workspaces.py` с фиксированным allowlist четырёх workspaces;
- ownership исправляется на `HERMES_UID:HERMES_GID` только при обнаруженном расхождении;
- origin отсутствующий добавляется, а SSH или иной URL заменяется на фиксированный HTTPS URL;
- `hermes-coders.service` запускает reconcile от root до preflight;
- все Compose lifecycle commands используют base и runtime Compose files;
- `runtime_smoke.py` остаётся обязательным `ExecStartPost` и `ExecReload` guard;
- добавлены функциональные и contract regression-тесты.

### Миграции и совместимость

Runs API, router payload и модельная маршрутизация не меняются. Изменение касается только запуска контейнеров и подготовки Git workspaces. Существующие `auth.json`, run journals, secrets и branches не удаляются.

После merge installer должен переустановить актуальный systemd unit. Временный production override можно удалить только после успешного запуска repository-managed unit и повторного smoke.

### Проверки

- regression contract проверяет отсутствие `/init` и наличие прямого Codex entrypoint;
- contract проверяет `GIT_CONFIG_GLOBAL` для обоих chat gateways;
- systemd contract проверяет reconcile, runtime Compose file и обязательный smoke;
- функциональный тест создаёт четыре временных Git workspaces и нормализует их SSH origins на HTTPS;
- отдельный тест проверяет вызов ownership repair до Git operations;
- live production до изменения репозитория уже подтвердил для Velvet и Max: `CHAT_OK`, `CODEX_AUTH_OK`, `LUNA_TERRA_SOL_OK`, `PUSH_OK` и health через `coderctl.py`.

### PR и commit

- PR: #570 `Закрепить production runtime Hermes coder`;
- ветка: `fix/hermes-coder-runtime-reconcile`;
- изменения опубликованы шестью узкими commits через GitHub contents API.

### Незавершённое

- дождаться полного CI;
- слить PR #570;
- обновить `/srv/velvet`;
- переустановить `hermes-coders.service` из репозитория;
- убрать временный production Compose override после контрольного smoke.

### Следующий шаг

Проверить CI draft PR #570, затем выполнить контролируемую миграцию production на repository-managed runtime contract.
