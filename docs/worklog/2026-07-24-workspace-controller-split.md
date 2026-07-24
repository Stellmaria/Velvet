# Сессия: разделение workspace archive и watermark controllers

- Дата: 2026-07-24
- ID: `2026-07-24-workspace-controller-split`
- Линия/фаза: workspace architecture cleanup
- Статус: `завершено`
- Ветка: `agent/workspace-controller-split`
- Базовый commit: `cc734a24edac3d1e16a697922cb9fcfb299d177a`

## Перед началом

### Цель

Разделить оставшийся смешанный Telegram controller `workspace_product_experience.py` на независимые контроллеры персонального архива и draft-watermark, сохранив текущие команды, callback data и порядок обработки.

### Исходный контекст

После удаления runtime wrappers файл всё ещё одновременно обслуживал `/archive`, переключение подсказок workspace home, `/watermark`, draft callbacks и ввод цвета watermark. Такое смешение затрудняло проверку границ и создавало риск конфликтов с legacy watermark router.

### Планируемый объём

- вынести обработку персонального архива в отдельный router;
- вынести draft-watermark command и callbacks в отдельный router;
- оставить в product experience только home preference flow;
- вынести общий разбор Telegram command token;
- подключить специализированные routers в явном порядке;
- добавить regression coverage архитектурных границ.

### Критерии готовности

- `workspace_product_experience.py` не содержит archive или watermark handlers;
- `/archive` сохраняет role и module checks;
- `/watermark` сохраняет draft workflow и workspace access checks;
- draft watermark router подключается раньше legacy watermark router;
- command parser поддерживает bot suffix и caption;
- новые и изменённые Python-файлы проходят синтаксическую проверку.

### Риски и ограничения

Срез не меняет callback data, тексты интерфейса, watermark service или хранение архива. Архивный controller пока использует существующие private presentation helpers из `workspace_owner_controls.py`; их публикация как явного контракта оставлена отдельным шагом.

## После завершения

### Фактически сделано

- добавлен `workspace_archive_controller.py` с archive command filter и handler;
- добавлен `workspace_watermark_draft_controller.py` с `/watermark`, draft callbacks и вводом цвета;
- добавлен `workspace_command_filtering.py` с единым command parser;
- `workspace_product_experience.py` сокращён до переключения подсказок home UI;
- `owner_menu.py` явно подключает archive, product experience и draft-watermark routers до legacy watermark router;
- добавлен `test_workspace_controller_split.py` с command и architecture regressions.

### Миграции и совместимость

Миграции не требуются. Команды `/archive` и `/watermark`, callback data, роли, module checks и пользовательские тексты сохранены.

### Проверки

- синтаксическая проверка новых и изменённых Python-файлов: success;
- сравнение ветки с `main`: только ожидаемые controller, composition, test и worklog changes;
- GitHub project notes contract повторно запускается после добавления этой записи;
- type check, tests и Docker build выполняются в PR CI.

### PR и commit

- PR: `#318 Split workspace archive and watermark controllers`;
- ветка: `agent/workspace-controller-split`.

### Незавершённое

В рамках этого среза функциональных незавершённых пунктов нет. Полный результат CI фиксируется в PR.

### Следующий шаг

Заменить private imports `_load_archive_characters` и `_archive_dashboard_keyboard` на явный archive presentation contract, затем отделить home hint controller от исторического имени `workspace_product_experience.py`.
