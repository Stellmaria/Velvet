# Сессия: классификация оставшихся handler implementations

- Дата: 2026-07-19
- ID: `2026-07-19-p3d-residual-handler-classification`
- Линия/фаза: Velvet Archive, P3D
- Статус: `частично`
- Ветка: `agent/p3d-residual-handler-classification`
- Базовый commit: `64d318bc2cd30556faa7f01a1e821ba7b844f3c8`

## Перед началом

### Цель

Определить и классифицировать пять последних физических implementations в `velvet_bot/handlers`, после того как все четыре domain bundles перешли на canonical presentation controllers.

### Исходный контекст

P3C завершён: root Router и domain bundles не импортируют `velvet_bot.handlers.*`, активных bundle routers 56, дублирующих регистраций 0. В handlers остаются 68 файлов, из которых 63 являются module aliases, а пять всё ещё содержат реальный код. Поисковый индекс GitHub показывает старые версии файлов, поэтому остаток должен определяться непосредственно текущим деревом в CI.

### Планируемый объём

- добавить машинный контракт остаточных implementations;
- получить точный набор имён из текущего checkout;
- классифицировать каждый файл как active nested controller, служебный module или устаревший остаток;
- перенести active controllers в presentation;
- удалить либо оставить с явным назначением не-router modules;
- не менять пользовательские функции, команды, callbacks и бизнес-логику;
- обновить architecture inventory и следующий P3D-срез.

### Критерии готовности

- набор пяти файлов явно записан и защищён тестом;
- каждый файл имеет подтверждённого runtime owner;
- скрытые imports из canonical controllers найдены;
- active controllers перенесены с module identity compatibility;
- legacy implementation count уменьшается до фактического минимального значения;
- tests, Docker build и project notes contract зелёные.

### Риски и ограничения

Один из известных кандидатов, `watermark.py`, является большим nested controller с файловым и Krita workflow. Его нельзя переносить или удалять без проверки порядка router inclusion и monkeypatch contracts. Первый CI этого PR используется как детерминированная инвентаризация, а не как доказательство готовности merge.

## После завершения

### Фактически сделано

- добавлен `tests/test_p3d_residual_handler_classification.py`;
- тест вычисляет implementations как handler-файлы без `P3_COMPAT_MODULE_ALIAS`;
- первый запуск намеренно использует discovery sentinel, чтобы CI напечатал точный остаток текущего дерева.

### Миграции и совместимость

Миграции не требуются. Runtime code на этапе discovery не изменяется.

### Проверки

- полный CI будет запущен через draft PR;
- ожидается один контролируемый failure discovery-контракта с точным набором файлов.

### PR и commit

- рабочая ветка: `agent/p3d-residual-handler-classification`;
- discovery contract commit: `bb019b885f5208205b4f9a7a2e72c5a08e7aaa18`;
- PR будет добавлен после запуска CI.

### Незавершённое

Точный набор файлов ещё не извлечён из CI. Перенос и compatibility retirement не начаты.

### Следующий шаг

Открыть draft PR, прочитать фактический residual set из test output, затем заменить sentinel на reviewed classification и продолжить перенос.
