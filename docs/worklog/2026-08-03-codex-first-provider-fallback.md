# 2026-08-03 — Codex-first routing с provider fallback

- Дата: `2026-08-03`
- ID: `hermes-codex-first-provider-fallback`
- Линия/фаза: `agents / coder orchestration`
- Статус: `draft PR`
- Базовый commit: `9216af7d0744248fd7dfa0eaf53b75cbb42b769a`

## Цель

Использовать ChatGPT-authenticated Codex как основной маршрут инженерных задач
Каэля и обоих прямых Telegram coder-ботов. Byesu остаётся резервом только для
новых задач, когда Codex недоступен из-за quota, auth или capacity, и только
если первичная попытка не изменила Git workspace.

## Архитектура

```text
Kael / direct Telegram coder
  -> project-scoped Codex runner
     -> codex_subscription: luna / terra / sol
     -> byesu_provider only on approved infrastructure failure
```

Каэль уже отправляет оркестрированные инженерные задачи через coder router.
Новый `codex-first` skill заставляет прямые Velvet/Max chat gateways сначала
делегировать инженерную задачу тому же project-scoped Codex runner.

## Безопасность

- fallback запрещён после изменения HEAD, текущей ветки, локальных refs,
  tracked или untracked state;
- после обнаруженной mutation runner не пробует другую Codex-модель;
- одна задача на проект выполняется последовательно существующим execution lock;
- provider key доступен только runner process и исключён из Codex shell;
- `GH_TOKEN` остаётся доступным coder shell для ветки, push и PR;
- route, model, fallback reason и mutation state сохраняются в run journal;
- ошибки тестов, плохой результат и пользовательская отмена не запускают fallback;
- после quota/auth failure основной route получает cooldown 30 минут;
- Librarian остаётся local-only.

## Изменения

- добавлен `deploy/hermes-coders/codex_first_runner.py`;
- добавлен `deploy/hermes-coders/codex_delegate.py`;
- runtime override переключает оба runners на Codex-first entrypoint;
- runtime override монтирует делегатор в оба chat gateways;
- Brain manifest добавляет skill только двум coder entities;
- добавлен contract/unit regression test.

## Проверки до production

- Python compile;
- focused unit/contract tests;
- обязательный repository CI;
- Compose config и Docker/runtime smoke после merge;
- controlled synthetic fallback test выполняется только на чистом test workspace;
- production rollout требует отдельного approved SHA и обновления QA runbook.
