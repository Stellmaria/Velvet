# Сессия: hotfix просроченных callback в медиасетах

- Дата: 2026-07-17
- ID: `2026-07-17-hotfix-quality-sets-stale-callback`
- Линия/фаза: production hotfix Velvet Archive
- Статус: в работе
- Ветка: `hotfix/quality-sets-stale-callback`
- Базовый commit: `80bc02439c7f75758841ab298d4da56c1f4594c0`

## Перед началом

### Цель

Устранить `TelegramBadRequest: query is too old and response timeout expired or query ID is invalid` в callback-обработчиках медиасетов.

### Исходный контекст

`handle_media_set_list()` сначала выполняет discovery, несколько PostgreSQL-запросов и редактирование сообщения, а затем вызывает `callback.answer()`. В production-логе обработка заняла 17,573 секунды, после чего Telegram отклонил просроченный callback.

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
- полный tests workflow, Docker build при срабатывании filters и project notes contract проходят.

### Риски и ограничения

- нельзя подавлять все `TelegramBadRequest`;
- нельзя переносить тяжёлую работу в фон без отдельного lifecycle;
- нельзя смешивать hotfix с Фазой 18N;
- нельзя менять правила создания, отклонения и выбора медиасета.

## После завершения

Заполняется после реализации.