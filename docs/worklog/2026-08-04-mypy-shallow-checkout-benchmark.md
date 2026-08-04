# Сессия: shallow checkout для mypy fast path

- Дата: `2026-08-04`
- ID: `mypy-shallow-checkout-benchmark-20260804`
- Линия/фаза: `CI performance / non-test required checks`
- Статус: `завершено`
- Ветка: `ci/mypy-shallow-checkout-20260804`
- Базовый commit: `6aa4f49ae27725e1bdc26de52c94fedeb5562d47`
- Связанный PR: `#608`

## Перед началом

### Цель

Устранить обнаруженную контрольным замером регрессию mypy fast path: тяжёлые
шаги корректно пропускались, но `fetch-depth: 0` загружал все ветки репозитория
и делал пустой required check медленнее прежнего полного mypy job.

### Исходный контекст

- полный mypy job на PR `#580`: около `10.7 с` по timestamps job log;
- fast-path mypy job на PR `#602`: около `16.1 с`;
- основная задержка fast path: полный fetch refs, примерно `13.6 с`.

### Планируемый объём

- заменить full-history checkout точного PR head на shallow checkout;
- загрузить exact base SHA отдельным shallow fetch;
- сохранить fail-closed определение изменённой mypy surface и fallback по имени
  base branch;
- добавить regression contract на настройки checkout;
- выполнить контрольный docs-only benchmark после merge.

### Критерии готовности

- `mypy-bounded` остаётся обязательным status context;
- bounded Python changes по-прежнему запускают setup, locked install и mypy;
- нерелевантные изменения проходят явный fast path;
- exact-head required CI зелёный;
- контрольный benchmark подтверждает сокращение времени fast path.

### Риски и ограничения

- GitHub runner startup и сетевой шум остаются вне контроля workflow;
- отдельный exact base fetch добавляет небольшой сетевой запрос;
- fallback `base_ref` сохранён для fail-closed восстановления при отсутствии
  exact SHA;
- изменение не оптимизирует другие workflow с full-history checkout.

## После завершения

### Фактически сделано

- exact PR head checkout ограничен `fetch-depth: 1`;
- exact base SHA загружается отдельным `git fetch --depth=1`;
- fallback определения base branch сохранён;
- добавлен workflow contract, запрещающий возврат `fetch-depth: 0` в bounded
  mypy job.

### Миграции и совместимость

- миграции базы данных отсутствуют;
- production runtime, Docker images и зависимости не изменены;
- required context `mypy-bounded` и его имя сохранены;
- hash-locked dependency install для реального mypy check сохранён.

### Проверки

- полный required CI запускается на exact head PR `#608` после синхронизации с
  актуальным `main`;
- contract test проверяет shallow head checkout и exact shallow base fetch;
- тяжёлые setup/install/mypy шаги остаются условными по bounded surface;
- после merge запланирован отдельный docs-only контрольный PR.

### PR и commit

- PR: `#608`;
- актуальная база: `6aa4f49ae27725e1bdc26de52c94fedeb5562d47`;
- workflow commit после синхронизации: `5c74acfc528df2acba8587842c2bfcbec7ed7c78`;
- contract-test commit: `f85eaf8c8f7f64b62bc5034e7fd62261fc5d40f8`.

### Незавершённое

- дождаться зелёного required CI на синхронизированном head;
- слить PR `#608` в `main`;
- открыть отдельный docs-only benchmark PR;
- снять итоговую длительность mypy fast path и закрыть benchmark PR без merge.

### Следующий шаг

После зелёного exact-head CI слить PR `#608`, выполнить одноразовый docs-only
контрольный прогон и зафиксировать фактическое ускорение относительно PR `#602`.
