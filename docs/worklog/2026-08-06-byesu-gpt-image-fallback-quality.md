# Сессия: Byesu routing и качество GPT Image 2

- Дата: 2026-08-06
- ID: `2026-08-06-byesu-gpt-image-fallback-quality`
- Линия/фаза: Ауф media generation / provider reliability
- Статус: частично
- Ветка: `feat/byesu-image-fallback-quality`
- Базовый commit: `7b561b0bb2d04b7d5fd4fa3ae084d9af830c424f`
- PR: #663
- Архитектурные обязательства: #458, #459

## Перед началом

### Цель

Добавить для существующего GPT Image 2 определённый Codex-first маршрут и ровно две Byesu image-модели с автоматическим выбором по параметрам запроса. Сохранить пользовательский выбор Sol/Terra/Luna и reasoning effort, исключить двойную генерацию и ложное обещание качества.

### Исходный контекст

До этой работы GPT Image 2 не имел полного единого контракта для Codex-first 1K, прямого Byesu-маршрута для 2K/4K, лимитного preflight и выбора image-модели по числу референсов. Hermes runtime при этом уже имел tier-aware routing, release graph и fail-closed требования, которые нельзя было обходить отдельным ad-hoc provider path.

После начала PR в `main` были дополнительно слиты #666 и #662. Поэтому ветка была синхронизирована с актуальным `main`, а конфликт в `velvet_bot/app/composition.py` разрешён с сохранением retirement legacy delivery installers из #662 и нового GPT Image quality stage из #663.

### Планируемый объём

- добавить Byesu image adapter и детерминированную routing policy;
- добавить Codex subscription-limit preflight для 1K;
- поддержать 1K, 2K и 4K без двойной media generation;
- сохранить Sol/Terra/Luna и разрешённые reasoning effort;
- ограничить промт 8000 символами, референсы шестью файлами по 8 МБ;
- включить runtime sources в compose, release graph, source guard и systemd contracts;
- добавить Telegram quality UI без отдельной новой composition stage;
- обновить operator/product docs и focused tests;
- синхронизировать архитектурные inventories и canonical docs после добавления нового production-модуля.

### Критерии готовности

- 1K сначала использует Codex, кроме доказанного активного исчерпания подписки;
- 2K/4K идут через Byesu `firefly-gpt-image-2`;
- fallback после фактического tool execution запрещён;
- один запрос создаёт не более одного изображения;
- provider credential contract согласован для Mini/Terra/Luna;
- package, repository и Telegram navigation inventories воспроизводимы;
- required GitHub checks зелёные;
- production rollout не выполняется в рамках merge этого PR без отдельной эксплуатационной процедуры.

### Риски и ограничения

- live provider availability и биллинг нельзя доказать только unit-тестами;
- stale subscription snapshot должен работать fail-open, иначе возможен ложный отказ от Codex;
- fallback после начала tool execution создаёт риск двойного списания и поэтому запрещён;
- новый installer-like UI-модуль увеличивает зарегистрированный архитектурный debt и обязан быть отражён в baseline, а не скрыт ослаблением тестов;
- production credentials и значения токенов не должны попадать в логи, worklog или repository artifacts.

## После завершения

### Фактически сделано

Реализованы `byesu_image_fallback.py`, `byesu_image_routing_policy.py` и `codex_image_limit_preflight.py`; обновлены Hermes runners, compose runtime, source guard, sandbox contract и systemd release graph. В Telegram добавлен `auf_gpt_image_2_quality_install.py`, а composition сохраняет единый bounded GPT Image stage.

Итоговый продуктовый контракт:

- пользовательский промт: до 8000 символов;
- референсы: 0–6, каждый до 8 МБ;
- анализатор: `gpt-5.6-luna`, `gpt-5.6-terra` или `gpt-5.6-sol`;
- reasoning effort: low, medium, high, xhigh или max;
- качество: 1K, 2K или 4K;
- фактических генераций: ровно одна.

Для 1K свежий активный limit snapshot с 100% usage или явным rate-limit пропускает Codex и выбирает Byesu. Неоднозначный, устаревший или недоступный preflight работает fail-open. До первого tool execution чистый subscription limit остаётся допустимым fallback-сигналом. При 0–3 референсах используется `gpt-image-2`, при 4–6 используется `firefly-gpt-image-2`.

Для 2K/4K Codex пропускается: выбранная GPT-5.6 модель формирует компактный generation prompt, затем `firefly-gpt-image-2` выполняет одну media generation. Silent truncation и автоматический перевод промта ради длины не используются.

После синхронизации с #662 сохранено удаление legacy delivery installers. Hermes tier smoke обновлён под единый `byesu-shared` credential group без ослабления fail-closed проверок. Package architecture baseline пересчитан штатным генератором: 656 production modules, 144054 LOC и 523 зарегистрированных package violations; shared-contract summary остаётся 3830 функций, 180 transitional private accesses и 0 blocking known contracts.

### Миграции и совместимость

SQL-миграций нет. Старые payload продолжают читать поле `resolution`; stale payload без значения используют 1K в новом UI-contract. Telegram delivery и queue task type не меняются. Изменения Hermes runtime входят в существующий release graph и не создают отдельный долговечный provider lifecycle.

### Проверки

Выполнены и прошли focused contracts для Byesu model selection, routing policy, prompt contract, image limit classification, Telegram GPT Image UI, Hermes release graph и unified tier-provider smoke. Package architecture и repository layout inventories пересчитаны штатными генераторами; их focused tests прошли.

Полный protected CI после этих исправлений выявил только оставшиеся синхронизации generated Telegram navigation inventory, canonical architecture docs и данного worklog contract. Security checks, branch-protection contract и mypy на проверенном head проходили. После следующего commit полный required CI должен быть запущен заново; зелёный финальный статус до его завершения не заявляется.

Обязательные live-проверки перед production остаются отдельными:

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

### PR и commit

- PR: #663 `GPT Image 2: Codex-first routing with Byesu model selection`.
- Ветка: `feat/byesu-image-fallback-quality`.
- Базовый commit сессии: `7b561b0bb2d04b7d5fd4fa3ae084d9af830c424f`.
- Ветка дополнительно синхронизирована с `main` после merge #666 и #662; конфликт composition разрешён вручную с сохранением обоих контрактов.
- Финальный squash commit определяется только после прохождения protected CI.

### Незавершённое

- пересобрать generated Telegram navigation inventory для 656 Python-файлов;
- синхронизировать текущий архитектурный срез в `development_status`, `project_memory` и `ARCHITECTURE_AUDIT`;
- дождаться полного required CI после этих изменений;
- выполнить live provider/media smoke существующими production credentials без публикации секретов;
- production deploy и restart не входят в текущую незавершённую CI-работу.

### Следующий шаг

Синхронизировать generated navigation и canonical docs, повторно прогнать protected CI и только при полностью зелёном required наборе выполнить squash merge PR #663. После merge дождаться штатного `publish-image.yml`, чтобы следующий production rollout использовал immutable digest, построенный именно из нового `main`.
