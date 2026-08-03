# 2026-08-03 — Codex-first routing с provider fallback

- Дата: `2026-08-03`
- ID: `hermes-codex-first-provider-fallback`
- Линия/фаза: `agents / coder orchestration`
- Статус: `частично`
- Ветка: `agent/codex-first-provider-fallback`
- Базовый commit: `9216af7d0744248fd7dfa0eaf53b75cbb42b769a`

## Перед началом

### Цель

Использовать ChatGPT-authenticated Codex как основной маршрут инженерных задач
Каэля и обоих прямых Telegram coder-ботов. Byesu должен оставаться резервом
только для новых задач, когда Codex недоступен из-за quota, auth или capacity,
и только если первичная попытка не начала исполнение и не изменила Git workspace.

### Исходный контекст

Каэль уже отправляет оркестрированные инженерные задачи через
`hermes-coder-router` в отдельные project-scoped Codex runners Velvet и Max.
Прямые Telegram coder gateways при этом продолжали работать как Hermes/Byesu
chat и не использовали включённый лимит Codex как основной инженерный маршрут.

У обоих проектов уже существуют отдельные `CODEX_HOME`, ChatGPT auth,
workspaces, Runs API keys и GitHub credentials. Требовалось добавить единый
Codex-first контракт, не смешивая проекты, не меняя production checkout и не
допуская автоматического повторения уже начатой изменяющей задачи.

### Планируемый объём

- добавить Codex-first runner поверх существующей model routing;
- классифицировать только quota, auth и capacity failures как основания fallback;
- блокировать повтор после изменений HEAD, branch, refs, tracked или untracked state;
- дополнительно блокировать повтор после появления primary execution events;
- добавить делегатор для прямых Telegram coder gateways Velvet и Max;
- подключить новый skill только к двум coder entities;
- сохранить route, model, fallback reason и mutation evidence в run journal;
- добавить unit/contract regressions и repository worklog;
- открыть только draft PR без merge, deployment или изменения production.

### Критерии готовности

- инженерная задача сначала направляется в ChatGPT-authenticated Codex;
- Byesu запускается только при подтверждённом quota, auth или capacity failure;
- provider fallback запрещён после Git mutation или primary execution events;
- ошибка тестов, плохой результат и отмена владельцем не запускают fallback;
- Velvet и Max сохраняют отдельные workspaces, auth и credentials;
- Librarian остаётся local-only;
- обязательные tests, type check, project notes, security и Docker checks проходят;
- production rollout выполняется только после merge и утверждения нового SHA.

### Риски и ограничения

- provider fallback использует отдельный временный `CODEX_HOME`; его реальная
  совместимость должна быть проверена controlled smoke на чистом test workspace;
- fail-closed проверка primary stdout может блокировать fallback даже при
  диагностическом JSONL без реальной мутации, что безопаснее двойного выполнения;
- direct coder skill попадёт в runtime Brain packs только после штатного reconcile;
- PR не меняет secrets и не запускает production migration автоматически;
- общий лимит Codex остаётся общим для аккаунта и двух project runners.

## После завершения

### Фактически сделано

- добавлен `deploy/hermes-coders/codex_first_runner.py`;
- добавлен fail-closed wrapper `codex_first_safe_runner.py`;
- добавлен `deploy/hermes-coders/codex_delegate.py`;
- runtime override переключает оба runners на safe Codex-first entrypoint;
- runtime override монтирует делегатор в оба chat gateways;
- Brain manifest добавляет `codex-first` skill только Velvet/Max coder entities;
- добавлены route, fallback и mutation fields в persistent run journal;
- добавлен cooldown primary route после quota/auth failure;
- добавлены focused unit и deployment contract regressions;
- открыт draft PR `#572` из отдельной feature-ветки;
- production и frozen QA checkout не изменялись.

### Миграции и совместимость

SQL-миграций нет. Формат существующего Runs API и router payload сохраняется.
Существующие Telegram, GitHub, Byesu и Codex credentials не заменяются и не
копируются между проектами. Новые Python entrypoints подключаются через tracked
`compose.runtime.yaml`.

После merge потребуется новый approved SHA, штатный context reconcile, rebuild
coder containers и controlled runtime smoke. Текущий production SHA
`3745713ffcab1ef3561bfdfed28ab7b6bf87a2f8` остаётся без изменений.

### Проверки

- локальный Python compile новых entrypoints: PASS;
- focused policy/contract tests до публикации: PASS;
- GitHub type check для опубликованного PR head: PASS;
- project notes contract выявил неверную структуру worklog; исправлено этим commit;
- tests, Docker build и security workflows должны быть подтверждены на новом head;
- provider fallback runtime smoke намеренно не выполнялся на production.

### PR и commit

- PR: `#572` — draft `Перевести coder-агентов на Codex-first с Byesu fallback`;
- ветка: `agent/codex-first-provider-fallback`;
- base: `9216af7d0744248fd7dfa0eaf53b75cbb42b769a`;
- изменения опубликованы последовательными узкими commits через GitHub Contents API;
- merge и production rollout не выполнялись.

### Незавершённое

- получить зелёный полный CI на актуальном head;
- проверить Compose config и запуск контейнеров после merge;
- выполнить бесплатный Codex smoke для Velvet и Max;
- проверить synthetic quota/auth fallback только на чистом test workspace;
- утвердить новый production SHA и обновить QA runbook перед rollout.

### Следующий шаг

Проверить повторный project notes contract и остальные обязательные workflows.
Исправить обнаруженные regressions в той же feature-ветке. После зелёного CI
провести review; merge и controlled production rollout выполнять отдельным
решением владельца.
