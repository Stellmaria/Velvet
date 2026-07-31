# Сессия: восстановление callback-цепочки генерации Ауф

- Дата: 1 августа 2026 года
- ID: `2026-08-01-auf-generation-callback-di`
- Линия/фаза: Velvet Bot / production hotfix генерации изображений
- Статус: `завершено`
- Ветка: `agent/fix-auf-generation-callback-di`
- Базовый commit: `58ae151fab0d4af771697fea2b59cbd3b11a7166`

## Перед началом

### Цель

Устранить возврат пользовательского сценария Qwen, Wan и FLUX к выбору модели после финального подтверждения стоимости и восстановить стабильную обработку callback-действий Ауф.

### Исходный контекст

В production после экрана с рассчитанной стоимостью генерация не завершала ожидаемый переход. Диагностический bundle `velvet_diagnostics_20260731T213622Z(1).zip` зафиксировал incident #461: callback-цепочка падала с `TypeError`, потому что `auf_wallet_ui_install` вызывал следующий обработчик без `auf_wallet_service` и `auf_purchase_service`.

Следующим слоем в установленной цепочке был `media_delivery_ui_install.handle_delivery_action`, чья явная сигнатура уже требовала оба сервиса. Отдельные тесты проверяли сигнатуры и payload моделей, но не проверяли сквозной passthrough зависимостей и финальное действие проблемных моделей.

### Планируемый объём

- передать оба wallet-сервиса через fallback `auf_wallet_ui_install`;
- добавить динамический регрессионный тест полного DI-контракта callback-wrapper;
- проверить callback финальной кнопки Qwen 2 Image Edit, Wan 2.7 Image и FLUX 2 Pro;
- подтвердить, что `photo_generate` попадает в enqueue-ветку и не вызывает fallback к выбору моделей;
- запустить обязательные GitHub Actions в отдельном PR.

### Критерии готовности

- callback-цепочка принимает и передаёт все 11 зависимостей без `TypeError`;
- финальная кнопка трёх проблемных моделей содержит действие `photo_generate`;
- canonical photo route вызывает постановку задачи в очередь;
- fallback для финального подтверждения не вызывается;
- tests, type check, docker build и project notes contract запускаются на PR.

### Риски и ограничения

Диагностический архив не содержит Telegram callback-data и содержимое пользовательских сообщений, поэтому production-причина подтверждается traceback и порядком установленных wrapper-слоёв. Живая проверка фактической генерации и списания выполняется после слияния и развёртывания нового `main`.

## После завершения

### Фактически сделано

- в `auf_wallet_ui_install.py` восстановлена передача `auf_wallet_service` и `auf_purchase_service` следующему обработчику;
- устранён разрыв между wallet-wrapper и media-delivery wrapper, вызвавший incident #461;
- добавлен тест, который устанавливает wallet-wrapper поверх обработчика с полной production-сигнатурой и проверяет точное сохранение всех аргументов;
- добавлен тест финальных клавиатур Qwen, Wan и FLUX;
- для каждого из трёх вариантов проверено, что callback `photo_generate` вызывает `_enqueue_auf_photo` и не уходит в fallback;
- открыт PR #526 с обязательным CI.

### Миграции и совместимость

Миграции базы данных не требуются. Формат callback-data, состояния FSM, расчёт цены, резервирование и provider payload не изменены. Исправление только восстанавливает уже объявленный DI-контракт между последовательно установленными обработчиками.

### Проверки

Синтаксис изменённого production-модуля проверен через Python AST. Добавлены unit-регрессии `test_wallet_wrapper_forwards_complete_dependency_contract` и `test_qwen_wan_and_flux_final_buttons_enqueue_instead_of_reopening_models`.

GitHub Actions `tests`, `type check`, `docker build` и `project notes contract` запущены на head PR.

### PR и commit

- PR: `#526 Исправить callback-цепочку генерации Qwen, Wan и FLUX`;
- production fix commit: `871172892acee6a6fbf2c12e618d9f2cd755b825`;
- regression tests commit: `7ebc1c4236b230db6cf3a6f02447964aa31ec891`.

### Незавершённое

- дождаться завершения обязательного CI;
- перевести PR из draft после зелёных проверок;
- слить PR в `main`;
- обновить production и повторить живой сценарий для Qwen, Wan и FLUX;
- убедиться, что incident #461 больше не повторяется.

### Следующий шаг

После зелёного CI слить PR #526, обновить сервер и пройти цепочку `модель → режим → исходные данные → параметры → стоимость → Да, создать` отдельно для Qwen, Wan и FLUX.
