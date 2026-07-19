# Сессия: P3C перенос analytics controllers в presentation

- Дата: 2026-07-19
- ID: `2026-07-19-p3c-analytics-controllers`
- Линия/фаза: P3C, физическая архитектура Telegram presentation
- Статус: `частично`
- Ветка: `agent/p3c-analytics-controllers-v2`
- Базовый commit: `d9d812fc7b35e04d5e1a36b6a6a4d03e6eabdbe0`

## Перед началом

### Цель

Переместить пять активных analytics Telegram controllers из `velvet_bot/handlers` в canonical presentation-пакет без изменения команд, callback prefixes, порядка регистрации или monkeypatch-совместимости старых импортов.

### Исходный контекст

После завершения archive/public, publication, references и characters/stories slices analytics bundle всё ещё импортировал пять активных реализаций напрямую из `velvet_bot.handlers`. Старые тесты и вспомогательные модули использовали эти пути для monkeypatch и прямых импортов, поэтому простое удаление файлов нарушило бы совместимость.

### Планируемый объём

- перенести `channel_analytics` в canonical analytics presentation package;
- перенести dashboard, dashboard overrides, discussion overrides и management controller;
- заменить старые handler-файлы короткими module aliases;
- переключить analytics bundle на canonical paths в прежнем порядке;
- обновить source-path contracts и architecture inventory;
- добавить отдельный регрессионный тест module identity;
- не менять SQL, миграции, команды, callbacks и пользовательские тексты.

### Критерии готовности

- старый и новый imports возвращают один module object;
- legacy handler-файлы не содержат router decorators;
- canonical modules владеют реальными Router implementations;
- analytics bundle содержит пять canonical imports в прежнем порядке;
- число активных bundle routers остаётся 56;
- legacy implementations уменьшаются с 35 до 30, aliases увеличиваются с 33 до 38;
- tests, Docker build и project notes contract проходят.

## После завершения

### Фактически сделано

- создан пакет `velvet_bot/presentation/telegram/routers/analytics_controllers`;
- перенесены пять активных analytics controllers;
- старые handler-пути заменены module aliases через `sys.modules`;
- analytics bundle переключён на canonical modules без изменения include order;
- Phase 9, discussion navigation и analytics management contracts направлены на canonical source;
- добавлен `tests/test_p3c_analytics_controllers.py`;
- architecture inventory обновлён до 30 implementations и 38 aliases;
- следующим P3C-срезом обозначены core operations presentation controllers.

### Миграции и совместимость

Миграции PostgreSQL не требуются. Команды `/analytics`, `/channelstats`, `/promptstats`, `/hashtagstats`, `/characterstats`, callback prefixes и порядок регистрации сохранены. Legacy imports остаются рабочими и указывают на те же canonical module objects.

### Проверки

CI будет запущен после открытия PR. Финальные номера проверок и число тестов будут добавлены после зелёного прогона.

### PR и commit

- ветка: `agent/p3c-analytics-controllers-v2`;
- PR ещё не открыт;
- базовый `main` уже включает admin archive controls и shared topic links из PR #201.

### Незавершённое

Нужно открыть draft PR, получить полный CI, исправить возможные stale source-path contracts и перевести worklog в `завершено`.

### Следующий шаг

После merge начать P3C перенос core operations controllers с нового `main`.
