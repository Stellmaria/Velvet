# Selective test surfaces и fast paths

- Дата: 2026-08-04
- ID: `selective-test-surfaces-2026-08-04`
- Линия/фаза: CI reliability и сокращение feedback loop
- Статус: `частично`
- Ветка: `ci/selective-test-surfaces-20260804`
- Базовый commit: `d13ce72c65a620e2e84f48ac6bbf96b0b1c9f2ce`

## Перед началом

### Цель

Не запускать четыре PostgreSQL test shard для изменений, которые не затрагивают основной код Velvet, БД или зависимости. Сохранить обязательный check context `unit-tests`, fail-closed поведение для неизвестных путей и периодический полный прогон.

### Исходный контекст

После PR #596 Docker CI уже выбирает только изменённые image surfaces. Type-check и security частично используют `scripts/ci_changed_surfaces.py`. Однако `.github/workflows/tests.yml` на каждый pull request безусловно поднимает четыре PostgreSQL, устанавливает зависимости в четырёх jobs и запускает полный sharded suite даже для документации, CI contracts и изолированных Hermes/Krita изменений.

Обязательный branch-protection context `unit-tests` нельзя убирать или делать path-filtered на уровне всего workflow: отсутствующий required check оставит PR в вечном ожидании. Поэтому оптимизация должна сохранять агрегатор и переводить только внутренние jobs в `success` или ожидаемый `skipped`.

### Планируемый объём

1. Расширить `ci_changed_surfaces.py` тестовыми поверхностями.
2. Разрешать fast path только для заранее известных docs, CI, Hermes и Krita путей.
3. Любой неизвестный, смешанный с application code или пустой change set направлять в полный suite.
4. Добавить отдельный `resolve-test-surfaces` job с актуальным merge-base против current base branch.
5. Оставить preflight обязательным для всех PR.
6. Запускать targeted contract tests без PostgreSQL для CI, Hermes и Krita.
7. Запускать четыре PostgreSQL shards только при `tests_full=true`.
8. Сохранить `unit-tests` как обязательный агрегатор и валидировать ожидаемые success/skipped состояния.
9. Добавить ежедневный полный scheduled run и ручной full run.
10. Перевести bounded mypy selector на current base ref вместо потенциально устаревшего PR base SHA.

### Критерии готовности

- docs-only PR не запускает PostgreSQL shards;
- CI-only PR запускает CI contracts, но не полный suite;
- Hermes-only PR запускает `test_hermes_*.py`, но не полный suite;
- Krita-only PR запускает `test_krita_*.py`, но не полный suite;
- application, DB, dependency и неизвестные пути запускают полный suite;
- mixed fast/application change запускает полный suite;
- `unit-tests` остаётся обязательным и не проходит при неожиданном skip/failure;
- nightly/manual события запускают полный suite;
- selector использует exact PR head и current base ref;
- полный CI PR проходит.

### Риски и ограничения

- targeted contracts не заменяют Docker smoke для Krita/Hermes images;
- fast path разрешён только для явно перечисленных путей, поэтому новые подсистемы по умолчанию будут медленными, но безопасными;
- изменение общего compose, lock-файлов или application code намеренно сохраняет полный suite;
- production runtime, deploy и branch-protection settings этим PR не меняются;
- фактическое сокращение времени измеряется на последующих docs/CI/Hermes/Krita PR.

## После завершения

### Фактически сделано

- добавлены тестовые surfaces `tests_ci`, `tests_hermes`, `tests_krita`, `tests_docs_only`, `tests_targeted`, `tests_full`;
- `tests_full` работает fail-closed для неизвестных и пустых change sets;
- `tests.yml` разделён на selector, обязательный preflight, targeted contracts, conditional shards и обязательный aggregator;
- добавлен nightly full run и `workflow_dispatch`;
- bounded mypy использует current base ref и exact PR head;
- добавлены selector и workflow regression contracts.

### Миграции и совместимость

Миграций БД и production config нет. Имя required check `unit-tests` сохраняется. Полный test shard workflow, PostgreSQL setup, dependency installation и shard plan не изменены внутри полного режима.

### Проверки

Запланированы и добавлены контракты для docs/CI/Hermes/Krita fast paths, application/dependency/unknown full fallback, mixed changes, current base ref, nightly full run и обязательного aggregator. Фактический GitHub Actions CI будет зафиксирован после открытия PR.

### PR и commit

PR создаётся после публикации начальной реализации. Текущий head фиксируется после завершения CI и review.

### Незавершённое

- PR ещё не открыт;
- GitHub Actions ещё не подтвердил реальный fast path;
- security selector пока не переведён на current base ref в этом commit set;
- фактическое время docs/CI/Hermes/Krita PR ещё не измерено.

### Следующий шаг

Открыть draft PR, проверить фактический `resolve-test-surfaces` output и убедиться, что текущий CI-only change запускает targeted contracts, а четыре PostgreSQL shards получают `skipped`. После зелёного CI выполнить итоговый diff review и обновить worklog.
