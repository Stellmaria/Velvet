# Сессия: восстановление Byesu model chain и lifecycle coder-router

- Дата: 2026-08-03
- ID: 2026-08-03-byesu-provider-model-chain
- Линия/фаза: server operations / Codex-first provider fallback
- Статус: частично
- Ветка: fix/byesu-provider-model-chain
- Базовый commit: 798e959b1f0cde636df0d97c3438f20de831b427

## Перед началом

### Цель

Вернуть существующую Byesu-цепочку `gpt-5.4-mini -> gpt-5.6-terra -> gpt-5.6-luna` как ограниченный fallback после недоступности ChatGPT-authenticated Codex subscription и восстановить автоматический lifecycle старого `coderctl -> coder-router` контура основного Hermes.

### Исходный контекст

После Codex-first rollout основной маршрут успешно использовал Codex Luna, Terra и Sol, но provider fallback был сведён к одной `gpt-5.6-terra`. Конфигурация Hermes всё ещё содержала Mini, Terra и Luna с двумя Byesu credentials. Одновременно перезапуск `hermes-coders.service` не поднимал неактивный `hermes-coder-router.service`, поэтому основной Каэль получал `URLError`, хотя coder-контейнеры были healthy.

### Планируемый объём

- отделить allowlist Byesu от allowlist Codex;
- восстановить цепочку Mini, Terra, Luna и два credential group;
- запретить retry после Git mutation или tool/file execution;
- не повторять Terra после auth/quota ошибки Mini на том же credential;
- публиковать безопасные capabilities и фактические attempted routes;
- связать lifecycle coder-router с `hermes-coders.service`;
- добавить startup smoke обоих проектов;
- покрыть policy и deployment contract тестами.

### Критерии готовности

- Codex subscription остаётся первым маршрутом;
- provider chain по умолчанию равна Mini, Terra, Luna;
- singular env сохраняет обратную совместимость;
- неизвестные и повторяющиеся provider models отклоняются;
- Mini/Terra используют coder credential, Luna использует GPT Pro credential;
- auth/quota на Mini пропускает Terra с тем же credential;
- capacity может перейти к следующей provider model;
- обычная ошибка, mutation или execution event прекращают retry;
- после старта coder runtime systemd поднимает и проверяет coder-router;
- production не меняется до merge и отдельного server reconcile.

### Риски и ограничения

- CI не выполняет реальные запросы к Byesu;
- systemd dependency проверяется контрактными тестами, а live restart только на VPS;
- live fallback нельзя проверять искусственным исчерпанием production-подписки без отдельного контролируемого smoke;
- основной Hermes продолжает использовать изолированный `coderctl -> coder-router`, а не прямой API key coder-контейнера.

## После завершения

### Фактически сделано

- добавлен отдельный provider catalog для Mini, Terra и Luna;
- добавлена переменная `CODEX_PROVIDER_FALLBACK_MODELS` с обратной совместимостью singular env;
- для каждой модели создаётся отдельный временный `CODEX_HOME`;
- capabilities показывают порядок моделей и безопасные credential groups;
- ledger записывает только реально выполненные provider routes;
- auth/quota блокирует оставшиеся модели того же credential group;
- capacity продолжает цепочку;
- обычная ошибка, Git mutation и execution events прекращают provider retry;
- обе Compose services используют полную Byesu-цепочку;
- `hermes-coders.service` теперь хочет `hermes-coder-router.service`;
- router unit является `PartOf` coder runtime и выполняет smoke обоих проектов после start/reload;
- добавлены targeted policy и lifecycle contract tests.

### Миграции и совместимость

Схема Runs API не меняется. Поля `provider_fallback.model`, `attempted_models` и `attempted_routes` сохранены. `provider_fallback.model` теперь содержит первую модель цепочки, а новое поле `models` показывает полный порядок. Старое `CODEX_PROVIDER_FALLBACK_MODEL` продолжает задавать одиночную модель, если plural env отсутствует.

### Проверки

- `python3 -m py_compile` для изменённых Python-файлов: PASS;
- targeted provider-chain tests: PASS;
- router lifecycle contract tests: PASS;
- совокупно локально: 10 tests, PASS;
- GitHub type check первого head: PASS;
- project notes первого head выявил отсутствующие обязательные разделы; worklog исправлен.

### PR и commit

- Draft PR: #574 `Восстановить Byesu model chain и lifecycle coder-router`;
- ветка: `fix/byesu-provider-model-chain`;
- базовый production/main commit: `798e959b1f0cde636df0d97c3438f20de831b427`;
- актуальный head хранится в PR #574 и обновляется отдельными проверочными commits;
- merge и deployment не выполнялись, production не менялся.

### Незавершённое

- дождаться полного GitHub CI;
- выполнить review и merge;
- установить обновлённые systemd units;
- перезапустить coder runtime и подтвердить `coderctl.py health all`;
- выполнить контролируемый live smoke provider chain без production mutation.

### Rollback

Вернуть singular `CODEX_PROVIDER_FALLBACK_MODEL=gpt-5.6-terra`, предыдущий entrypoint и удалить lifecycle dependency/smoke router unit. Production rollback должен выполняться только отдельной разрешённой операцией.

### Следующий шаг

Дождаться зелёного CI на PR #574 и выполнить code review. После отдельного разрешения на merge обновить production, установить systemd units, перезапустить только Hermes coder runtime и проверить обе capabilities, `coderctl.py health all` и безопасный Telegram handoff без merge/deploy со стороны агента.
