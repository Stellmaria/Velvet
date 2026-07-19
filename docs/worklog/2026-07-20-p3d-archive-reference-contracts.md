# Сессия: P3D archive/reference contracts

- Дата: 2026-07-20
- ID: `2026-07-20-p3d-archive-reference-contracts`
- Линия/фаза: Velvet Archive, P3D
- Статус: `в работе`
- Ветка: `agent/p3d-archive-reference-contracts`

## Перед началом

### Цель

Убрать следующую связанную группу production-зависимостей от `velvet_bot.handlers.*`: parsing-функции архива и референсов, callback contracts и presentation helpers, которые уже имеют канонические реализации.

### Исходный контекст

После PR #221 legacy baseline составляет 19 consumer-файлов, 28 references и 17 legacy modules. Следующий безопасный срез включает archive/reference consumers и несколько прямых callback imports, которые можно перевести без изменения поведения.

### Планируемый объём

- вынести parsing-функции save/reference flows в публичные модули;
- перевести archive guest и reference controllers на публичные imports;
- убрать imports `handlers.admin_directory` из reference help;
- классифицировать и очистить связанные public archive/media presentation imports;
- обновить AST inventory и regression tests;
- удалить legacy alias только если его consumer count станет нулевым;
- не менять callback prefixes, команды, SQL и пользовательские тексты.

### Критерии готовности

- очищенные controllers не импортируют `velvet_bot.handlers`;
- parsing functions имеют один публичный источник истины;
- compatibility exports остаются только для внешних/тестовых consumers;
- legacy baseline уменьшается;
- полный test suite, Docker build и project notes contract проходят.

### Риски и ограничения

Импорт controller-to-controller заменяется публичным contract/helper module, а не новым универсальным `utils.py`. Handler alias удаляется только при нулевом production consumer count и наличии regression-проверки.
