# Сессия: явные presentation contracts watermark

- Дата: 2026-07-24
- ID: `2026-07-24-watermark-presentation-contracts`
- Линия/фаза: workspace architecture cleanup
- Статус: `завершено`
- Ветка: `agent/watermark-presentation-contracts`
- Базовый commit: `20ff548be9cc3d759637869d4db566c022a2a87f`

## Перед началом

### Цель

Убрать runtime-подмены watermark formatter/keyboard и Krita wake policy из `install_workspace_product_experience()`.

### Исходный контекст

После переноса persistence в domain boundary workspace installer всё ещё подменял функции `watermark_ui`, импортированные функции core/service/public archive и `_wake_krita`. Draft-aware UI и правило отложенного запуска Krita существовали только благодаря порядку импортов и mutation глобальных объектов.

### Планируемый объём

- сделать `watermark_ui.build_watermark_keyboard()` канонически draft-aware;
- сделать `format_watermark_caption()` канонически draft/error-aware;
- добавить общий публичный `wake_krita()` contract;
- не запускать Krita при открытии формы и создании draft;
- явно запускать Krita при генерации или pending revision;
- удалить watermark UI/wake monkeypatch из workspace installer;
- добавить UI, wake-policy и architecture regression-тесты.

### Критерии готовности

- canonical UI корректно отображает draft, pending/processing, error и ready/archive состояния;
- workspace installer не присваивает функции в watermark modules;
- форма и создание draft не вызывают Supervisor;
- generate/public archive pending flows используют общий wake contract;
- полный CI зелёный.

### Риски и ограничения

Home keyboard, workspace render wrappers, quick references и callback prefix compatibility остаются в installer. Они относятся к отдельным workspace presentation срезам. Схема БД и persistence не меняются.

## После завершения

### Фактически сделано

- `watermark_ui.build_watermark_keyboard()` теперь канонически обрабатывает `draft`, `error`, `pending`, `processing`, `ready` и archive review states;
- `format_watermark_caption()` формирует штатные сообщения для draft и error без runtime wrapper;
- добавлен общий публичный `wake_krita(context=...)` в `krita_supervisor.py`;
- форма watermark и создание draft больше не запускают Krita заранее;
- generate, обычные pending revisions и public archive watermark используют явный общий wake contract;
- из workspace installer удалены присваивания функций в `watermark_ui`, core watermark, service и public archive modules;
- удалены `_draft_watermark_keyboard`, `_draft_watermark_caption`, `_defer_krita_start` и `_ORIGINAL_CORE_WAKE_KRITA`;
- существующие тесты draft UI переведены на канонический `build_watermark_keyboard`;
- добавлены UI, Supervisor wake-policy и architecture regression-тесты.

### Миграции и совместимость

Миграции не требуются. Callback actions `generate` и `draft_noop` сохраняются. Ready/archive keyboards, persistence contract и прежние pending-вызовы service остаются совместимыми.

### Проверки

- focused compileall: success;
- focused presentation, existing draft UI, persistence boundary и reliability tests: success;
- tests `1824`: success;
- type check `477`: success;
- Docker build `1229`: success;
- project notes contract `1102`: success.

### PR и commit

- PR: `#314 Replace watermark UI and Krita runtime patches with explicit contracts`;
- ветка: `agent/watermark-presentation-contracts`;
- implementation head перед финализацией журнала: `b1a22a25449749952bca853f893e87d7db4fc1ce`.

### Незавершённое

- после merge выполнить smoke test: форма не запускает Krita, кнопка generate запускает её и переводит draft в обработку;
- home/render/quick-keyboard workspace wrappers и callback prefix compatibility остаются отдельными срезами.

### Следующий шаг

Убрать оставшиеся cross-controller workspace UI monkeypatch небольшими отдельными PR.
