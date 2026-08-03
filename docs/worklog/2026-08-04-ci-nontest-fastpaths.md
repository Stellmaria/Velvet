# Сессия: ускорение обязательных CI-проверок вне тестов

- Дата: 2026-08-04
- ID: 2026-08-04-ci-nontest-fastpaths
- Линия/фаза: CI performance / required checks
- Статус: частично
- Ветка: `agent/ci-nontest-fastpath-20260804`
- Базовый commit: `ebcfc943410a700a356f98c413b13512e4d3e13c`

## Перед началом

### Цель

Сократить критический путь обязательных GitHub Actions проверок вне unittest-шардов без удаления required status checks и без отказа от ежедневной полной проверки безопасности.

### Исходный контекст

Security workflow последовательно запускал supply-chain contract, static security и image security, хотя проверки не зависят от результатов друг друга. CodeQL, mypy, dependency audit и image scan выполняли полный объём даже при изменениях, не затрагивающих их поверхность. Project notes скачивал полную историю Git и отдельно устанавливал Python.

### Планируемый объём

- определить изменённые CI-поверхности единым тестируемым скриптом;
- сохранить названия обязательных jobs и зелёный статус для нерелевантных изменений;
- убрать искусственные зависимости между security jobs;
- запускать CodeQL, mypy, dependency audit и image scan только для релевантных изменений;
- добавить ежедневный полный security scan;
- добавить GitHub Actions layer cache для production image scan;
- сократить checkout и отменять устаревшие project-notes runs;
- закрепить поведение contract-тестами.

### Критерии готовности

- required jobs `mypy-bounded`, `codeql-python`, `codeql-actions`, `supply-chain-contract`, `static-security`, `image-security` и `notes` сохраняются;
- изменение соответствующей поверхности запускает полный профиль проверки;
- нерелевантное изменение завершает тяжёлую проверку быстрым успешным путём;
- scheduled и manual security runs выполняют полный профиль;
- security jobs не сериализованы через `needs`;
- локальные contract-тесты и полный GitHub Actions CI проходят.

### Риски и ограничения

- корректность быстрых путей зависит от полноты таблицы поверхностей;
- GitHub-hosted runner всё равно тратит время на запуск job и checkout;
- Docker cache может отсутствовать на первом прогоне или быть недоступен для записи, поэтому экспорт cache настроен как необязательный;
- ежедневный полный scan остаётся необходимым для обнаружения новых CVE без изменений dependency files.

## После завершения

### Фактически сделано

- добавлен `scripts/ci_changed_surfaces.py`, вычисляющий изменённые пути и флаги для supply chain, static tools, dependency audit, CodeQL, image scan и bounded mypy;
- добавлены contract-тесты для классификации путей и структуры workflow;
- security jobs переведены на параллельный запуск без `needs`;
- добавлен ежедневный полный security run в `03:23 UTC`;
- CodeQL, dependency audit, supply-chain rebuild и image scan получили быстрые пути;
- image security использует Buildx cache backend `type=gha`;
- bounded mypy запускает тяжёлые шаги только при изменении своей области;
- project notes использует `fetch-depth: 2`, системный Python, прямой base SHA и отмену устаревших запусков.

### Миграции и совместимость

Схемы данных, production runtime, Docker Compose, application API и required check names не меняются. Изменяется только способ выбора тяжёлых шагов внутри существующих GitHub Actions jobs. Scheduled security run добавлен как дополнительная полная проверка.

### Проверки

- `python -m py_compile scripts/ci_changed_surfaces.py tests/test_ci_changed_surfaces.py` — успешно;
- `python -m unittest tests/test_ci_changed_surfaces.py -v` — 10 тестов успешно;
- изменённые workflow YAML разобраны локальным YAML parser — успешно;
- первый `project notes contract` выявил отсутствующие обязательные разделы этой записи; структура исправлена текущим коммитом;
- остальные GitHub Actions проверки выполняются в PR #580.

### PR и commit

- PR: #580;
- ветка: `agent/ci-nontest-fastpath-20260804`;
- базовый commit: `ebcfc943410a700a356f98c413b13512e4d3e13c`;
- merge выполняется только после полного зелёного CI.

### Незавершённое

- подтвердить повторный успешный project notes run;
- проверить полный GitHub Actions CI;
- исправить возможные несовместимости GitHub runner, Buildx cache или выражений workflow;
- после зелёного CI слить PR в `main`.

### Rollback

Вернуть прежние версии `.github/workflows/security.yml`, `.github/workflows/type-check.yml` и `.github/workflows/project-notes-contract.yml`, удалить `scripts/ci_changed_surfaces.py` и `tests/test_ci_changed_surfaces.py`.

### Следующий шаг

Дождаться полного результата CI для текущего head PR #580, исправить подтверждённые ошибки и выполнить squash merge в `main` после прохождения всех required checks.
