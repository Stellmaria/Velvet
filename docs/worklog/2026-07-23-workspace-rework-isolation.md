# Сессия: workspace rework isolation и пользовательский Qwen

- Дата: 2026-07-23
- ID: `2026-07-23-workspace-rework-isolation`
- Линия/фаза: personal workspace media controls и Qwen product
- Статус: `частично`
- Ветка: `agent/workspace-rework-isolation`
- Базовый commit: `f6ef9ed2f9e24b11d63a0635791eacba583f51a0`

## Перед началом

### Цель

Изолировать очередь доработки и дать участникам личных пространств полноценный Qwen без доступа к системному Quality Center Velvet. Проверки, решения, калибровка, история и отчёты одного workspace не должны пересекаться с системным или соседним архивом, даже если физический `media_id` дедуплицирован и используется в нескольких пространствах.

### Исходный контекст

`media_rework_items` имела глобальный первичный ключ только по `media_id`, а ручная заявка скрывала все связи файла. Пользовательский модуль Qwen показывал только переход к сравнению с референсом. Полная проверка качества использовала глобальную таблицу `media_ai_quality_checks`, поэтому безопасно открыть её личным пространствам было нельзя. Системные промт-сравнение, палитра, композиция и история AI-заданий также не имели workspace boundary.

### Планируемый объём

- изолировать rework items и events по `(workspace_id, media_id)`;
- сохранить системный Quality Center и его trigger в workspace `1`;
- добавить отдельное workspace-хранилище Qwen checks, feedback и job history;
- запускать локальный Qwen worker только для разрешённых и включённых пространств;
- дать reviewer+ просмотр и запуск анализа;
- дать editor+ решения «принять» и «на доработку»;
- добавить карточную проверку текущего архивного изображения;
- добавить проверку всего архива, очереди и разделы отчётов;
- добавить пользовательские workflows «промт против результата» и «палитра и композиция»;
- сохранить workspace-safe сравнение с референсом;
- добавить workspace-specific calibration по решениям редакторов;
- не открывать пользователям системную AI-очередь, медиасеты или калибровку Стэл.

### Критерии готовности

- один `media_id` имеет независимые rework и Qwen records в разных workspaces;
- личная заявка и решение не скрывают и не меняют системную или соседнюю связь;
- Qwen worker не берёт задания выключенного или запрещённого пространства;
- reviewer может запустить и прочитать отчёт, но не принять редакторское решение;
- editor/admin/owner может принять материал или отправить его на scoped-доработку;
- prompt/result, palette/composition и history сохраняются только в текущем workspace;
- system Quality Center продолжает работать через старые таблицы без изменения API;
- fresh migration order проходит на чистой PostgreSQL;
- tests, type check, Docker build, backup restore drill и project notes contract проходят.

### Риски и ограничения

Desktop Ollama/Qwen не проверяется GitHub Actions. CI подтверждает схему, роуты, типы и контейнер, но после merge потребуется живой тест с реально запущенной моделью. Пользовательский Qwen использует тот же локальный GPU lock, поэтому системная и пользовательская задачи выполняются последовательно, а не устраивают конкурс на уничтожение видеопамяти.

## После завершения

### Фактически сделано

- migration `z002_workspace_media_rework_isolation.sql` добавляет workspace scope в rework items/events и составные ключи;
- ручное скрытие и публичная видимость ограничены текущим workspace;
- migration `z003_workspace_qwen_product.sql` создаёт `workspace_qwen_checks`, `workspace_qwen_feedback` и `workspace_qwen_jobs`;
- quality check primary key равен `(workspace_id, media_id)`;
- feedback-trigger сохраняет решение и калибровочный outcome только своего workspace;
- repository проверяет принадлежность изображения пространству, ведёт очередь, отчёты, решения, ошибки, калибровку и историю;
- worker выбирает задания только при `module.is_allowed`, `module.is_enabled` и `workspace_settings.qwen_enabled`;
- зависшее после рестарта quality-задание может быть повторно захвачено через 15 минут, а прерванная интерактивная задача помечается ошибкой в истории через 30 минут;
- system и personal Qwen используют один local AI lock;
- в Qwen-меню личного пространства добавлены проверки архива, полный аудит, prompt/result, palette/composition, references и history;
- на карточке архивного изображения появилась кнопка `🤖 Qwen-проверка`;
- reviewer+ может запускать и читать отдельные проверки;
- полный аудит всего архива и редакторские решения доступны editor/admin/owner;
- editor+ может принять результат или создать workspace-scoped rework hold;
- повторная проверка существующей scoped-доработки переводит её в `ready_for_review` после завершения Qwen;
- prompt/result и palette/composition выполняются немедленно, сохраняют workspace job и доступны в истории;
- старый reference comparison остаётся workspace-scoped и открывается из общего Qwen-меню;
- callback prefix и FSM формы добавлены в guarded workspace access middleware;
- старый reference-only Qwen entry перехватывается новым ранним personal router до generic owner controls;
- generated P2 stability, repository layout и Telegram navigation inventories обновлены после добавления Qwen-модулей.

### Миграции и совместимость

Добавлены additive migrations `z002_workspace_media_rework_isolation.sql` и `z003_workspace_qwen_product.sql`. Глобальные таблицы системного Quality Center не изменялись. Старые system repository/service/worker и команды Стэл продолжают использовать прежние API. Личный Qwen хранится отдельно, поэтому одинаковый `media_id` может безопасно иметь разные отчёты и решения.

### Проверки

Первый расширенный head `96a0a732cf001df176bc01f2ded0a7483b93495e`: type check `398`, Docker build `1165`, backup restore drill `369` и project notes `1034` прошли. Tests `1745` обнаружили только устаревшие generated inventories и неточный source-contract тест. Inventories были воспроизведены штатными генераторами, assertion исправлен, recovery и role boundaries усилены. Финальный полный CI выполняется на новом head.

### PR и commit

Draft PR `#307 Enable isolated Qwen for personal workspaces` содержит rework isolation и полный personal workspace Qwen product. Финальный head и merge commit будут записаны после зелёного CI.

### Незавершённое

- дождаться полного CI после обновления generated inventories и hardening;
- исправить возможные оставшиеся failures;
- перевести draft PR в ready и слить в `main`;
- выполнить `Supervisor → Update`, применить `z002` и `z003`;
- провести живой сценарий с reviewer и editor в личном workspace;
- проверить один quality report, prompt/result, palette/composition и history на реальном Ollama/Qwen.

### Следующий шаг

Получить зелёный CI, слить PR, затем в Telegram включить пользователю модуль Qwen, открыть личный архив, нажать Qwen на изображении и проверить, что отчёт и решение остаются только в выбранном workspace.
