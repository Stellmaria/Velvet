# Сессия: workspace rework isolation

- Дата: 2026-07-23
- ID: `2026-07-23-workspace-rework-isolation`
- Линия/фаза: personal workspace media controls
- Статус: `частично`
- Ветка: `agent/workspace-rework-isolation`
- Базовый commit: `f6ef9ed2f9e24b11d63a0635791eacba583f51a0`

## Перед началом

### Цель

Изолировать очередь доработки по пользовательским пространствам. Заявка владельца личного архива должна скрывать и блокировать материал только в его пространстве, не затрагивая системный архив или другой workspace, даже когда один дедуплицированный `media_id` связан с несколькими персонажами.

### Исходный контекст

`media_rework_items` имела глобальный первичный ключ только по `media_id`, `request_manual_rework()` скрывала все строки `character_media` этого файла, а публичная видимость исключала материал при любой активной заявке независимо от workspace. Кнопка личной карточки отправляла материал в общую очередь, а завершить такую заявку из пользовательского пространства было нельзя.

### Планируемый объём

- добавить `workspace_id` в элементы и события очереди;
- заменить первичный ключ на `(workspace_id, media_id)`;
- сохранить системный Qwen-trigger в workspace `1`;
- ограничить ручное скрытие только связями текущего пространства;
- сделать repository workspace-scoped с совместимым default `1`;
- исключать материал из публичной выдачи только при активной заявке его workspace;
- перехватить личные actions `rework` и `public` раньше generic owner handler;
- превратить кнопку в понятный цикл «начать / завершить»;
- запретить возврат в публичный архив до завершения scoped-заявки;
- проверить один общий media ID, связанный с двумя пространствами.

### Критерии готовности

- один `media_id` может иметь независимые rework items в разных workspaces;
- личная заявка не скрывает системную или соседнюю связь файла;
- system Quality Center продолжает работать через workspace `1`;
- повторное нажатие владельца завершает scoped-заявку;
- завершение не публикует материал автоматически;
- возврат в публичный архив заблокирован только активной заявкой текущего workspace;
- fresh migration order проходит на чистой PostgreSQL;
- tests, type check, Docker build, backup restore drill и project notes contract проходят.

### Риски и ограничения

Личный rework пока не запускает отдельную Qwen-перепроверку: retry остаётся системной операцией workspace `1`, поскольку global `media_ai_quality_checks` всё ещё имеет один ключ на `media_id`. Личное пространство получает безопасный manual hold и ручное завершение. Полная workspace-scoped AI-проверка потребует отдельной миграции quality checks.

## После завершения

### Фактически сделано

- новая миграция `z002_workspace_media_rework_isolation.sql` выполняется после `z001` на чистой базе;
- `media_rework_items` и `media_rework_events` получили обязательный `workspace_id` с backfill в system workspace `1`;
- item primary key и event foreign key стали составными;
- quality trigger переписан на system workspace `1` и composite conflict target;
- `request_manual_rework()` проверяет принадлежность файла и скрывает только ссылки выбранного workspace;
- `MediaReworkRepository` принимает workspace и изолирует summary/list/get/is_active/resolve;
- Qwen accept/retry остаются доступными только системному workspace;
- public visibility сопоставляет активную заявку с workspace персонажа;
- добавлен ранний router личной карточки для начала/завершения доработки и безопасного возврата в public;
- кнопка и справка описывают двухэтапный lifecycle;
- интеграционный тест связывает один `media_id` с system и personal workspace и проверяет независимость видимости и очереди.

### Миграции и совместимость

Добавлена additive migration `z002_workspace_media_rework_isolation.sql`. Старый `z001` не изменяется. Все старые вызовы repository и manual request без workspace продолжают использовать system workspace `1`. Существующие system queue handlers сохраняют API.

### Проверки

GitHub Actions будут запущены после открытия draft PR. Особое внимание требуется fresh database migration, PostgreSQL integration cases, router inventories и backup restore drill.

### PR и commit

Draft PR будет открыт из `agent/workspace-rework-isolation` в `main`. Финальный head, номера CI и merge commit будут добавлены после зелёного полного workflow.

### Незавершённое

- открыть draft PR;
- исправить замечания tests/type check/Docker/backup restore/project notes;
- после merge выполнить `Supervisor → Update` и проверить применение `z002`;
- провести живой сценарий двумя workspace;
- отдельно спроектировать workspace-scoped Qwen recheck, если он нужен владельцам личных архивов.

### Следующий шаг

Открыть PR и проверить сценарий: общий Telegram-файл сохранён в system и personal workspace → personal owner ставит hold → system material остаётся публичным → personal owner завершает hold → отдельно возвращает personal material в public.
