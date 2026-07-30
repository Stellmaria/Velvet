# 2026-07-30 — исправление активного worker доставки Ауф

- Дата: 2026-07-30
- ID: `auf-active-delivery-worker-fix`
- Линия/фаза: AI media generation / result delivery
- Статус: `завершено`
- Ветка: `agent/fix-active-delivery-worker-v2`
- Базовый commit: `39868c73e6a0b24f524d5801df715dde5dd87a7e`

## Перед началом

### Цель

Исправить production-регрессию, при которой GRS AI завершает платную генерацию, прогресс достигает 100%, но пользователь не получает ни оригинальный файл, ни предпросмотр, а в разделе «Мои задачи» отсутствует кнопка повторной доставки.

### Исходный контекст

Предыдущий recovery installer менял `_deliver_best_effort` у `FriendlyKieGenerationWorker`. Production после установки GRS resilience использует `ResilientFriendlyKieGenerationWorker`, который переопределяет этот метод и обходил исправление. Его собственная доставка отправляла provider URL напрямую и молча завершалась при `TelegramAPIError`.

Кнопка повторной доставки также создавалась только при уже сохранённом `result_urls`, поэтому не помогала задачам, где provider task id сохранился, а URL результата в `ai_tasks.result` отсутствовал.

### Планируемый объём

- патчить фактический класс `app.workers.KieGenerationWorker` после всех GRS composition installers;
- показывать кнопку доставки для каждой успешной media-задачи;
- при отсутствии URL восстанавливать результат через provider task id;
- сохранять восстановленные URL обратно в `ai_tasks.result`;
- не создавать новую provider-задачу и не выполнять повторное списание.

### Критерии готовности

- будущая успешная генерация проходит через recovery delivery;
- успешная задача получает кнопку `📤 Доставить` даже без сохранённого URL;
- GRS result endpoint используется только для чтения уже существующей задачи;
- восстановленные URL сохраняются в БД;
- полный CI проходит.

### Риски и ограничения

Provider может удалить временный asset или вернуть задачу без URL. В этом случае бот показывает явную ошибку. Восстановление не запускает генерацию повторно и потому не может пересоздать уже удалённый provider asset.

## После завершения

### Фактически сделано

- добавлен installer `install_auf_active_delivery_fix` после базового delivery recovery;
- installer получает фактический `workers.KieGenerationWorker` и заменяет его `_deliver_best_effort`;
- экран задач показывает кнопку доставки для всех успешных media-задач;
- provider task id читается из `ai_tasks.result`, payload или `kie_campaign`;
- при отсутствии `result_urls` бот повторно читает существующую задачу GRS/Kie, сохраняет найденные URL и вызывает штатную повторную доставку;
- проверка владельца и workspace остаётся в базовом recovery;
- добавлены regression-тесты на активный worker, callback limit и задачу без сохранённого URL.

### Миграции и совместимость

SQL-миграций нет. Формат `ai_tasks.result` не меняется: используются существующие поля `provider_task_id` и `result_urls`. Старые успешные задачи можно восстановить, если provider task id сохранился и asset ещё доступен.

### Проверки

- unit/integration tests;
- type check;
- Docker build;
- project notes contract;
- generated inventories.

### PR и commit

- PR: `#456`;
- итоговый commit фиксируется после зелёного CI и merge.

### Незавершённое

- в будущем вынести post-processing результатов в отдельную durable delivery queue вместо runtime installers.

### Следующий шаг

После зелёного CI слить hotfix, обновить Supervisor и повторно доставить задачу `964ef056-bebe-4723-b963-ca3dc56bcdeb` из «Ауф → Кошелёк → Мои задачи» без новой генерации и списания.
