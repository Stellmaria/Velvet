# Сессия: hotfix просроченных callback в медиасетах

- Дата: 2026-07-17
- ID: `2026-07-17-hotfix-quality-sets-stale-callback`
- Линия/фаза: production hotfix Velvet Archive
- Статус: завершено
- Ветка: `hotfix/quality-sets-stale-callback`
- Базовый commit: `80bc02439c7f75758841ab298d4da56c1f4594c0`

## Перед началом

### Цель

Устранить `TelegramBadRequest: query is too old and response timeout expired or query ID is invalid` в callback-обработчиках медиасетов.

### Исходный контекст

`handle_media_set_list()` сначала выполнял discovery, несколько PostgreSQL-запросов и редактирование сообщения, а затем вызывал `callback.answer()`. В production-логе обработка заняла 17,573 секунды, после чего Telegram отклонил просроченный callback.

### Планируемый объём

- подтверждать callback списка до тяжёлой загрузки;
- подтверждать открытие кандидата до последовательной отправки preview;
- добавить точечный safe-answer для уже просроченных callback;
- не скрывать остальные `TelegramBadRequest`;
- применить safe-answer к соседним обработчикам этого файла;
- добавить regression-тест порядка вызовов и фильтра ошибки;
- обновить changelog;
- прогнать полный CI.

### Критерии готовности

- `handle_media_set_list()` отвечает callback до `show_media_set_candidates()`;
- `handle_media_set_open()` отвечает до `_send_candidate_previews()`;
- точная ошибка stale/invalid callback не создаёт ERROR;
- другие Telegram Bad Request продолжают пробрасываться;
- бизнес-операции медиасетов и SQL не меняются;
- полный tests workflow, Docker build и project notes contract проходят.

### Риски и ограничения

- нельзя подавлять все `TelegramBadRequest`;
- нельзя переносить тяжёлую работу в фон без отдельного lifecycle;
- нельзя смешивать hotfix с Фазой 18N;
- нельзя менять правила создания, отклонения и выбора медиасета.

## После завершения

### Фактически сделано

- добавлен `_safe_callback_answer()` с точечным подавлением только expired/invalid callback response Telegram;
- другие `TelegramBadRequest` продолжают пробрасываться;
- `handle_media_set_list()` подтверждает нажатие до discovery, SQL и редактирования сообщения;
- `handle_media_set_open()` подтверждает нажатие до последовательной отправки preview;
- соседние обработчики create, ignore, toggle и error branches используют единый safe-answer;
- toggle подтверждает результат до редактирования сообщения;
- бизнес-операции медиасетов, SQL и модели не изменялись;
- добавлены regression-тесты фильтра исключения и порядка подтверждения;
- changelog обновлён.

### Миграции и совместимость

Миграции, таблицы, SQL и callback payload не изменены. Изменён только порядок Telegram acknowledgment и обработка точного протухшего callback ответа.

### Проверки

- `project notes contract #43` — успешно;
- полный workflow `tests #560` с PostgreSQL 16 — успешно;
- `docker build #154` — успешно;
- после этой финальной записи CI запускается повторно на окончательном head перед merge.

### PR и commit

- PR: #109 `Hotfix: подтверждать callback медиасетов до долгих операций`;
- зелёный промежуточный head: `032b0272f9b69e4cb971bd0d98e06584d5e5cdcd`;
- финальный squash commit фиксируется GitHub при слиянии PR #109.

### Незавершённое

Обязательных пунктов hotfix не осталось. Для фактического запуска на Windows потребуется обновить локальный `main` и перезапустить Velvet Bot через Supervisor.

### Следующий шаг

После слияния hotfix продолжить Фазу 18N из отдельной ветки, предварительно перебазировав её на обновлённый `main`.