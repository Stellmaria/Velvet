# Сессия: Supervisor test DB, workspace slug и Telegram network noise

- Дата: 2026-07-22
- ID: `2026-07-22-supervisor-test-slug-network-fix`
- Линия/фаза: deployment reliability hotfix
- Статус: `частично`
- Ветка: `agent/supervisor-test-slug-network-fix`
- Базовый commit: `7f824a1836aff68639f0e4a817204344119a3835`

## Перед началом

### Цель

Разблокировать обновление через Supervisor при локальном `TEST_DATABASE_URL` без прав на `public`, устранить повтор slug личного архива после удаления и убрать временные Telegram network failures из CRITICAL-инцидентов.

### Исходный контекст

Supervisor после fast-forward запускал все 1162 теста с унаследованным `TEST_DATABASE_URL`. Локальная PostgreSQL-роль не имела CREATE в `public`, поэтому 81 integration test падал до выполнения сценария и update откатывался. Создание нового личного архива использовало `owned + 1`, из-за чего существующий или осиротевший slug `user-<id>-1` вызывал unique violation. Ошибки ClientConnectorError из root ErrorEvent логировались как CRITICAL, хотя соединение Telegram восстанавливается повтором.

### Планируемый объём

- изолировать PostgreSQL integration tests в отдельной схеме;
- не наследовать `TEST_DATABASE_URL` в Supervisor без явного `SUPERVISOR_TEST_DATABASE_URL`;
- сохранить совместимость первого update, который выполняет старая версия Supervisor;
- заменить count-based slug на collision-resistant значение;
- классифицировать временные Telegram transport exceptions до CRITICAL-логирования;
- автоматически закрыть старые непросмотренные сетевые инциденты;
- добавить regression tests и обновить generated inventories.

### Критерии готовности

- старый Supervisor способен принять commit без доступа к `public`;
- production bot никогда автоматически не переключается в тестовую схему;
- повторное создание архива не повторяет slug;
- ClientConnectorError и WinError 121/1236 не создают CRITICAL incident;
- реальные исключения обработчиков остаются CRITICAL;
- tests, type-check, Docker и project notes contract проходят.

### Риски и ограничения

Для полноценного локального запуска PostgreSQL integration tests роль должна иметь CREATE на отдельной тестовой базе или использовать готовую `TEST_DATABASE_SCHEMA`. Если это невозможно, unittest корректно помечает такие integration cases как skipped вместо 81 ложной ошибки. GitHub CI продолжает выполнять их на выделенном PostgreSQL.

## После завершения

### Фактически сделано

- добавлена unittest-only изоляция PostgreSQL схемы;
- добавлен явный `SUPERVISOR_TEST_DATABASE_URL`;
- унаследованный `TEST_DATABASE_URL` удаляется из post-update test subprocess;
- workspace slug переведён на UUID suffix;
- transient Telegram ErrorEvent логируется на INFO;
- старые сетевые root incidents включены в startup cleanup;
- добавлены regression tests.

### Миграции и совместимость

SQL-миграция не требуется. Production `DATABASE_URL` и его search_path не меняются. Изоляция включается только при запуске `unittest` и точном совпадении DSN с `TEST_DATABASE_URL`.

### Проверки

Ожидается полный GitHub Actions CI.

### PR и commit

Будут заполнены после публикации.

### Незавершённое

После merge требуется повторить Supervisor update на Windows и проверить автоматическое закрытие сетевых инцидентов #60 и #62. Исправленный incident #61 можно отметить прочитанным после успешного повторного создания архива.

### Следующий шаг

После зелёного CI слить hotfix и повторить update через Supervisor.
