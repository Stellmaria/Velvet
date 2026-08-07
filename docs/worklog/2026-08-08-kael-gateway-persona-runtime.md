# Kael gateway persona runtime compatibility

- Дата: 2026-08-08
- ID: kael-gateway-persona-runtime
- Линия/фаза: Hermes operator identity and Telegram gateway reliability
- Статус: `завершено`
- Ветка: `fix/kael-gateway-persona-runtime`
- Базовый commit: `89489278602af0eaf01e7f87212ef6b07dba9790`

## Перед началом

### Цель

Гарантировать, что основной Hermes operator во всех пользовательских интерфейсах, включая Telegram, идентифицирует себя как Каэль Велвет и сохраняет каноническую persona даже на Hermes gateway builds, которые не загружают `SOUL.md` при создании Telegram session.

### Исходный контекст

После успешного production update и canonical `deploy/hermes-orchestration/install.sh` Kael context был compiled, installed и verified, основной Hermes container был перезапущен, а `/opt/data/SOUL.md` содержал явный identity contract Каэля. Несмотря на это, на вопрос владельца «как тебя зовут?» Telegram gateway ответил «Hermes Agent» и описал generic upstream persona.

Repository contract подтвердил, что `brain-vault/manifest.json` назначает `deploy/hermes-operator/SOUL.kael.md` сущности `kael`, а `install_context_pack.py` атомарно устанавливает этот SOUL в основной Hermes data directory. Следовательно, проблема находилась после установки context pack, на gateway/session prompt boundary.

Upstream Hermes history содержит известный gateway compatibility defect: старые gateway builds создавали agent без загрузки SOUL identity и использовали built-in `Hermes Agent` identity. Новые upstream builds загружают SOUL, но production image может быть закреплён или локально закэширован на более старом runtime.

### Планируемый объём

- Усилить canonical identity до «Каэль Велвет», сохранив операционные ограничения отдельно в AGENTS.
- Добавить compatibility bridge только для entity `kael`: verified SOUL должен также записываться в поддерживаемый gateway `agent.system_prompt`.
- Не менять coder или Librarian personas.
- Сохранять существующие `config.yaml` owner/mode и соседние настройки.
- Поддержать замену старого scalar и block-scalar `agent.system_prompt` без сохранения stale built-in identity text.
- Добавить regression tests на оба формата.

### Критерии готовности

- Установленный `/opt/data/SOUL.md` и `agent.system_prompt` содержат один и тот же verified Kael SOUL.
- `agent.system_prompt` содержит `Каэль Велвет`.
- Старый block prompt вида `You are Hermes Agent` удаляется при reconcile.
- Остальные `agent` и top-level config keys сохраняются.
- Permissions `config.yaml` не расширяются.
- Coder/Librarian install paths не получают Kael compatibility prompt.
- Protected CI проходит на final integrated PR head.

### Риски и ограничения

- Compatibility bridge намеренно дублирует один и тот же identity contract в двух system-level источниках на новых Hermes builds. Это предпочтительнее зависимости от mutable upstream image и не расширяет capabilities.
- Production rollout, Hermes restart и Telegram identity canary не входят в repo PR и выполняются отдельно после merge.
- Отдельный Codex SQLite runtime defect исправляется независимым PR и не смешивается с identity scope.

## После завершения

### Фактически сделано

- `deploy/hermes-operator/SOUL.kael.md` усилен до persona «Каэль Велвет» с однозначным запретом представляться Hermes/Hermes Agent/AI assistant и с более прямым, скептичным, технически въедливым характером, сухим сарказмом и строгим режимом для production incidents.
- `deploy/hermes-brain/install_context_pack.py` для `entity=kael`, `mode=hermes` синхронизирует verified SOUL в `agent.system_prompt` существующего `config.yaml`.
- Запись выполняется атомарно с сохранением owner, group и mode config file.
- Duplicate top-level `agent` sections или duplicate `agent.system_prompt` keys блокируют install fail-closed.
- Existing scalar и block-scalar prompt заменяются одним JSON-quoted YAML scalar; stale nested block content удаляется.
- Другие entities и Codex install mode не затронуты.

### Миграции и совместимость

SQL migrations отсутствуют. Persistent user memory не меняется. Compatibility bridge использует существующий Hermes `agent.system_prompt` contract и не требует новых secrets, ports, mounts или privileges.

На новых Hermes gateway builds SOUL продолжает загружаться штатно; system prompt содержит тот же verified identity и не вводит альтернативную persona. На старых builds compatibility prompt закрывает известный SOUL-loading gap.

### Проверки

- В `tests/test_hermes_brain_vault.py` добавлен regression на замену scalar `agent.system_prompt`, byte-equivalence с установленным SOUL, сохранение соседних keys и file mode.
- Добавлен regression на замену stale block-scalar identity без потери `agent.max_iterations` и следующего top-level section.
- Protected GitHub CI должен подтвердить final integrated tree перед merge.

### PR и commit

- Ветка: `fix/kael-gateway-persona-runtime`
- Base: `89489278602af0eaf01e7f87212ef6b07dba9790`
- PR и merge commit фиксируются после успешных protected checks.

### Незавершённое

Production пока не получает этот identity compatibility fix. После merge требуется штатный production update/reconcile и отдельный Telegram canary «как тебя зовут?» с ожидаемым ответом «Каэль» или «Каэль Велвет».

### Следующий шаг

Открыть PR, дождаться terminal success всех required checks, синхронизировать branch с актуальным `main` при необходимости и merge без обхода branch protection.
