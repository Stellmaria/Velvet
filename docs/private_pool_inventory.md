# Инвентаризация приватной PostgreSQL-границы

Дата среза: 17 июля 2026 года.
Базовый commit первоначальной инвентаризации: `172390deef5ced4fe1527701524b034a8646c87e`.
Последний завершённый срез: Фаза 18V, `AIQualityRepository`.

## Результат

AST-сканирование production package `velvet_bot/` фиксирует:

- 102 внешних обращения к `Database._require_pool()`;
- 26 production-файлов;
- внутреннее определение и использование внутри класса `Database` исключено из долга;
- tests, migrations и docs не входят в production-инвентаризацию;
- динамический `getattr(..., "_require_pool")` также контролируется.

Точный машинный baseline находится в `docs/private_pool_inventory.json`. Для каждого файла сохраняются число обращений и SHA-256 набора `access_kind + scope`. Номера строк выводятся сканером, но не входят в identity, чтобы обычное форматирование файла не требовало бессмысленного обновления baseline.

## Категории долга

| Категория | Обращений | Подход |
|---|---:|---|
| Legacy query-модули | 53 | постепенно превращать в repositories/queries, не ограничиваться заменой метода |
| Backup infrastructure | 17 | отдельный срез с сохранением restore/retention contracts |
| Repository-классы внутри крупных модулей | 16 | переводить по одному repository с runtime-тестами |
| Presentation handlers | 7 | вынести SQL и DB access из handlers в use case/repository |
| Compatibility-фасады | 5 | переводить после их штатных источников либо удалять после проверки импортов |
| Application/application-service | 4 | вынести persistence в repository boundary |

Всего: 102.

## Завершённые погашения baseline

- Фаза 18N: `ArchivePreviewRepository`, удалены 2 обращения и 1 production-файл.
- Фаза 18O: `PublicationValidationRepository`, удалены 2 обращения и 1 production-файл.
- Фаза 18P: `PublicationDraftRepository`, удалены 8 обращений и 1 production-файл; явные domain repositories закрыты.
- Фаза 18Q: `SystemRepository`, удалены 2 обращения и 1 production-файл; отдельный infrastructure repository закрыт.
- Фаза 18R: `PromptResultReportRepository`, удалено 1 обращение и 1 production-файл.
- Фаза 18S: `PaletteCompositionReportRepository`, удалено 1 обращение и 1 production-файл.
- Фаза 18T: `VelvetFormattingReportRepository`, удалено 1 обращение и 1 production-файл; одиночные report repositories закрыты.
- Фаза 18U: `QualityCalibrationRepository`, удалены 3 обращения и 1 production-файл; profile, pagination и case lookup переведены вместе.
- Фаза 18V: `AIQualityRepository`, удалены 8 обращений и 1 production-файл; claim, lifecycle, dashboard и owner decisions переведены вместе.

## Очередь

### Волна A. Repository-классы внутри модулей

1. **Фаза 18W:** repository-контур `ai_vision.py`, 4 connection points.
2. Error center и Ollama/resilient AI repositories отдельными срезами.

### Волна B. Infrastructure

- backup service/runtime;
- Telegram import persistence.

### Волна C. Старые query-модули

- analytics dashboard/review/reactions;
- channel analytics;
- character aliases;
- quality audit;
- media sets;
- public media lookup;
- discussion thread linking.

В этой волне сначала создаётся типизированная repository/query-граница. Механическая замена `_require_pool()` на `acquire()` без структурного переноса не считается завершением архитектурного долга.

### Волна D. Нарушения слоёв

Прямой DB access из `handlers/quality_set_ai.py`, `handlers/quality_sets.py` и `handlers/reference_comparison.py` переносится в application/domain services. Handler должен остаться Telegram-адаптером и не владеть SQL.

### Волна E. Compatibility cleanup

Compatibility-фасады переводятся после штатных модулей. Если фактических импортов больше нет, фасад удаляется отдельным безопасным PR.

## Команды

Полный отчёт с актуальными строками:

```bash
python scripts/inventory_private_pool.py
```

JSON-отчёт:

```bash
python scripts/inventory_private_pool.py --json
```

Проверка соответствия baseline:

```bash
python scripts/inventory_private_pool.py --check-baseline
```

Любое изменение известного набора должно происходить в отдельной фазе вместе с обновлением baseline, дневника и regression-тестов.
