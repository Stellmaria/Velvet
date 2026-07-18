# Рабочая сессия: Фаза 18W — MediaAIRepository и Database.acquire

Статус: частично

## Перед началом

### Цель

Перевести repository-контур `velvet_bot/ai_vision.py` с приватного доступа `Database._require_pool()` на публичную границу `Database.acquire()` без изменения SQL, транзакций и lifecycle семантического анализа медиа.

### Исходный контекст

- линия: основное развитие Velvet Archive;
- фаза: 18W;
- базовый commit: `bb6de424c35f0a5eb2a031599a43ab90e8143dea`;
- ветка: `agent/phase18w-ai-vision-acquire`;
- baseline до работы: 100 внешних обращений в 25 production-файлах;
- целевой модуль: `velvet_bot/ai_vision.py`, 4 connection points;
- техническое преобразование подготовлено отдельным одноразовым workflow, который удаляет себя из итогового diff.

### Планируемый объём

1. Перевести `MediaAIRepository.claim_targets()`, `mark_ready()`, `mark_error()` и `summary()` на `Database.acquire()`.
2. Сохранить claim transaction, stale recovery, `FOR UPDATE ... SKIP LOCKED`, batch transition в `processing`, JSONB profile persistence и aggregate mapping.
3. Добавить source/runtime regression-тест границы.
4. Обновить private pool inventory и проектную документацию.

### Критерии готовности

- в `MediaAIRepository` отсутствует `._require_pool()`;
- четыре repository-операции используют `self._database.acquire()`;
- baseline уменьшается до 96 обращений в 24 production-файлах;
- тесты Фазы 18W и общий inventory-контракт проходят;
- worklog, project memory, development status и changelog отражают результат.

### Риски и ограничения

- нельзя менять SQL и lifecycle существующей AI-очереди;
- нельзя смешивать Фазу 18W с Heavy Runtime/ResourceManager ТЗ;
- старые миграции не изменяются;
- живая проверка Ollama/Telegram в этот срез не входит.

### Стабилизационное обоснование

1. Улучшается существующая функция семантического анализа медиа.
2. Persistence становится понятнее и использует единую публичную PostgreSQL-границу.
3. Новая предметная область не добавляется.
4. Улучшение измеряется уменьшением AST baseline 100 → 96 и regression-тестами.
5. Сохраняются repository boundary, транзакция claim и текущий AI lifecycle.

## После завершения

Будет заполнено после реализации и CI.
