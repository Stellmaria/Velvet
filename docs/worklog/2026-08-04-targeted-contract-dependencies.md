# Сессия: зависимости targeted contract tests

- Дата: `2026-08-04`
- ID: `targeted-contract-dependencies-20260804`
- Линия/фаза: `CI reliability / selective test surfaces`
- Статус: `частично`
- Ветка: `fix/ci-targeted-contract-dependencies`
- Базовый commit: `0ab6001d67f16dff316361a4d875d181fe6a2828`
- Связанный PR: `#601`

## Перед началом

### Цель

Сохранить быстрый Hermes/Krita/CI test path без PostgreSQL, но запускать targeted
contract tests в том же зафиксированном Python dependency environment, что и
полный suite.

### Исходный контекст

После merge `#601` PR `#597` корректно выбрал `tests_hermes=true` и пропустил
четыре PostgreSQL shards. Targeted job завершился за минуты, но импорт
`tests/test_hermes_entities_contract.py` упал с
`ModuleNotFoundError: No module named 'asyncpg'`, потому что job не устанавливал
`requirements.lock`.

### Планируемый объём

- добавить pinned `setup-uv` в `targeted-contracts`;
- установить зависимости с `--require-hashes` из `requirements.lock`;
- не запускать PostgreSQL в targeted job;
- сохранить selective routing и обязательный `unit-tests` aggregator;
- добавить workflow contract для dependency setup.

## После завершения

### Фактически сделано

- targeted job использует `uv 0.11.16` с cache по `requirements.lock`;
- зависимости устанавливаются через
  `uv pip install --system --require-hashes -r requirements.lock`;
- targeted timeout увеличен с 6 до 8 минут для bounded cold-cache установки;
- cache из PR читается, но не публикуется (`save-cache: false`);
- regression contract проверяет pinned uv, hash-locked install и отсутствие
  PostgreSQL в targeted section.

### Совместимость и безопасность

- production runtime не изменяется;
- Docker images не изменяются;
- миграции отсутствуют;
- полный PostgreSQL suite остаётся обязательным для application, DB,
  dependency, mixed и unknown surfaces;
- targeted Hermes/Krita/CI paths по-прежнему не запускают PostgreSQL;
- required context `unit-tests` сохраняется.

### Критерии готовности

- workflow contract проходит;
- CI-only PR использует targeted path;
- targeted job успешно импортирует зависимости проекта;
- PostgreSQL shards остаются skipped;
- обязательные GitHub checks зелёные на exact head.

### Следующий шаг

Открыть отдельный PR, дождаться зелёного CI, выполнить merge и обновить PR
`#597` на исправленный `main` без изменения его terminal-status diff.
