# Сессия: canonical quick references keyboard

- Дата: 2026-07-24
- ID: `2026-07-24-workspace-quick-references-contract`
- Линия/фаза: workspace architecture cleanup
- Статус: `завершено`
- Ветка: `agent/workspace-quick-references-contract`
- Базовый commit: `8d4e9e7cb7f005ddc83a3de90a1d19097d5aa879`

## Перед началом

### Цель

Перенести кнопку `🧬 Референсы` из runtime-подмены `_quick_keyboard` в канонический builder быстрых действий workspace.

### Исходный контекст

`workspace_product_experience.py` сохранял оригинальный `_quick_keyboard`, строил поверх него дополнительную кнопку и во время установки присваивал wrapper обратно в `workspace_guided_actions`. Наличие кнопки зависело от импорта owner menu и вызова installer.

### Планируемый объём

- добавить references row прямо в `workspace_guided_actions._quick_keyboard`;
- сохранить условие показа только при включённом модуле `references`;
- удалить original alias, wrapper, импорт и runtime assignment из workspace installer;
- добавить functional и architecture regression coverage.

### Критерии готовности

- кнопка появляется без импорта workspace installer;
- кнопка отсутствует при выключенном модуле;
- callback ведёт в canonical workspace module route;
- installer не подменяет `_quick_keyboard`;
- focused и полный CI зелёные.

### Риски и ограничения

Срез не меняет callback data, module access checks, home keyboard, hint preferences или scoped command installation. Эти части остаются отдельными задачами.

## После завершения

### Фактически сделано

- references row добавлен в canonical `_quick_keyboard`;
- кнопка показывается только при активном модуле `references`;
- callback сохраняет canonical workspace module route;
- удалены `_ORIGINAL_QUICK_KEYBOARD`, wrapper, импорт и runtime assignment;
- добавлены functional и architecture regression-тесты;
- временные transformation script и workflow удалены из PR.

### Миграции и совместимость

Миграции не требуются. Callback остаётся `WorkspaceCallback(action="module", module_key="references")`.

### Проверки

- focused compileall: success;
- focused quick keyboard и workspace command tests: success;
- Telegram navigation contract: success;
- tests `1834`: success;
- type check `487`: success;
- Docker build `1237`: success;
- project notes contract `1110`: success.

### PR и commit

PR `#316` — `Make quick references part of canonical workspace UI`.

### Незавершённое

Нет в рамках этого среза.

### Следующий шаг

Убрать runtime wrappers home/render и заменить их явными параметрами канонического workspace UI.
