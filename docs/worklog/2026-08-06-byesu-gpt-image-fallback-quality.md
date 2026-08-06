# Сессия: Byesu routing и качество GPT Image 2

- Дата: 2026-08-06
- ID: `2026-08-06-byesu-gpt-image-fallback-quality`
- Линия/фаза: Ауф media generation / provider reliability
- Статус: частично
- Ветка: `feat/byesu-image-fallback-quality`
- PR: #663, draft
- Базовый commit: `7b561b0bb2d04b7d5fd4fa3ae084d9af830c424f`
- Архитектурные обязательства: #458, #459

## Цель

Добавить для существующего GPT Image 2 определённый Codex-first маршрут и ровно
две Byesu image-модели с автоматическим выбором по параметрам запроса. Сохранить
пользовательский выбор Sol/Terra/Luna и reasoning effort, исключить двойную
генерацию и ложное обещание качества.

## Итоговый продуктовый контракт

- пользовательский промт: до 8000 символов;
- референсы: от 0 до 6, каждый до 8 МБ;
- анализатор: `gpt-5.6-luna`, `gpt-5.6-terra` или `gpt-5.6-sol`;
- reasoning effort: low, medium, high, xhigh или max;
- качество: 1K, 2K или 4K;
- фактических генераций: ровно одна.

### 1K

Перед запуском runtime читает свежие окна подписки через Codex app-server.
Только явное активное исчерпание, `rate_limit_reached_type` либо 100% до будущего
`resets_at`, пропускает Codex и сразу запускает подходящий Byesu-route.

Если preflight недоступен, неоднозначен, показывает меньше 100% или уже прошедший
reset, поведение fail-open: Codex Plus запускается первым. Если он вызывает
`image_gen`, дальнейший provider fallback запрещён. Чистый `subscription_limit`
до первого tool execution остаётся страховочным Byesu-route:

- 0–3 референса → `gpt-image-2`;
- 4–6 референсов → `firefly-gpt-image-2`.

### 2K и 4K

Codex пропускается. Выбранная GPT-5.6 модель анализирует промт и референсы через
Byesu, затем `firefly-gpt-image-2` создаёт одно изображение выбранного качества.

## Промт после анализа

Исходный промт и отчёт анализатора не конкатенируются. GPT-анализатор создаёт
один финальный generation prompt, сохраняя пользовательскую сцену и добавляя
только устойчивые признаки внешности. Целевой размер — до 6500 символов,
абсолютный предел — 8000. Превышение завершает задачу до media generation;
silent truncation не используется.

Перевод всего промта на китайский ради числа символов запрещён: Unicode chars и
tokens не эквивалентны, а перевод способен менять смысл и приоритеты.

## Реализация

- `deploy/hermes-coders/byesu_image_fallback.py` — API adapter, capability gate,
  multimodal analysis и one-shot media call;
- `deploy/hermes-coders/byesu_image_routing_policy.py` — выбор image-модели,
  Codex-first 1K, прямой Byesu для 2K/4K и compact-prompt contract;
- `deploy/hermes-coders/codex_image_limit_preflight.py` — свежий limit probe,
  fail-open классификация и пропуск заведомо обречённого Codex generation;
- `deploy/hermes-coders/codex_context_launcher_runner.py` — установка runtime
  policies в порядке fallback → parameter routing → limit preflight;
- `deploy/hermes-coders/compose.runtime.yaml` — bind mounts, preflight settings и
  Velvet-only provider gate;
- `deploy/hermes-coders/runtime_source_guard.py` и systemd unit — release graph;
- `velvet_bot/app/auf_gpt_image_2_quality_install.py` — UI качества, маршрута,
  лимита 6 референсов и 8 МБ;
- `docs/gpt_image_2_codex.md` — операторский и продуктовый контракт;
- focused tests для model selection, prompt contract, limit classification, UI и
  runtime graph.

## Совместимость

SQL-миграций нет. Старые payload продолжают читать поле `resolution`; stale
payload без значения используют 1K в новом UI-contract. Telegram delivery и
queue task type не меняются.

## Проверки

Draft PR #663 создан для запуска CI. В текущей execution-среде checkout получить
не удалось из-за отсутствия DNS к GitHub, поэтому локальные tests, inventory и
live provider smoke не выполнены.

Добавлены unit-контракты:

- `rate_limit_reached_type` пропускает запуск Codex;
- активное окно 100% пропускает запуск Codex;
- 99%, прошедший reset и неизвестный snapshot работают fail-open;
- probe failure возвращает управление обычному Codex-route;
- preflight installer применяется после parameter routing;
- новый runtime source покрыт compose, import guard и systemd permissions.

Обязательные live-проверки перед production:

1. 1K через доступный Codex Plus;
2. preflight с 99% продолжает Codex-route;
3. preflight с активными 100% сразу выбирает Byesu;
4. недоступный preflight fail-open запускает Codex;
5. clean subscription limit до tool execution после неубедительного preflight;
6. fallback 1K с 0, 3, 4 и 6 референсами;
7. прямые 2K и 4K через firefly;
8. Sol/Terra/Luna и разрешённые effort;
9. capability mismatch без generation charge;
10. блокировка fallback после synthetic tool execution;
11. Telegram preview, original document и фактические размеры.

## Незавершённое

- дождаться CI и исправить failures;
- пересчитать package architecture inventory, если required check потребует;
- выполнить capability smoke существующим production token без публикации ключа;
- выполнить live media smoke и подтвердить списание/возврат;
- merge, deploy и restart не выполнять до зелёных проверок.