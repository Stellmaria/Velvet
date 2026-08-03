# Сессия: контракт защиты ветки main

- Дата: 2026-08-03
- ID: 2026-08-03-branch-protection-contract
- Линия/фаза: CI / repository governance
- Статус: готово к merge
- Ветка: ci/branch-protection-contract
- Базовый commit: ef5fc03c03b110652ce2ea79b12a37b2d0b9b3db

## Перед началом

### Цель

Закрепить для Velvet проверяемую защиту ветки `main`, чтобы pull request нельзя было слить без тестов, типизации, project notes, security supply chain и условной Docker-сборки.

### Исходный контекст

В репозитории уже работали отдельные CI workflows, но не было машинного контракта, подтверждающего фактическую настройку branch protection. Docker build запускался только для ограниченного набора путей, поэтому его нельзя было безопасно добавить как безусловный required check.

### Планируемый объём

- добавить job проверки classic branch protection;
- зафиксировать итоговые стабильные required checks;
- добавить постоянный Docker gate, который требует условный job `build` только для затронутой поверхности;
- настроить classic branch protection rule для `main`;
- повторно проверить правило через GitHub API перед merge.

### Критерии готовности

- `main` защищён от прямого merge без pull request;
- обязательные CI jobs записаны как required checks;
- Docker/runtime изменения требуют успешную сборку;
- обычные PR не блокируются отсутствующим path-filtered workflow;
- контракт branch protection проходит после настройки правила.

## После завершения

### Фактически сделано

- создан workflow `branch protection contract`;
- добавлен стабильный job `branch-protection-contract`;
- добавлен `docker-build-contract`, который определяет изменённую Docker/runtime поверхность;
- при релевантных изменениях gate ожидает check `build` для того же commit и требует conclusion `success`;
- настроено classic branch protection rule для `main`;
- зафиксированы десять обязательных CI contexts;
- ветка PR перебазирована на актуальный `main` без изменения функционального diff.

### Миграции и совместимость

Runtime-код, база данных и пользовательские сценарии не изменяются. Изменение касается только GitHub Actions и политики merge в `main`. Существующие path filters Docker workflow сохраняются.

### Проверки

- `docker-build-contract` проходит для нерелевантных Docker изменений;
- `branch-protection-contract` подтверждает фактическую защиту `main`;
- tests, type check, project notes и security workflows запускаются на актуальном head PR;
- merge разрешается только после полного зелёного набора required checks.

### PR и commit

- PR: #571 `ci: закрепить контракт защиты main`;
- ветка: `ci/branch-protection-contract`;
- актуальная база: `ef5fc03c03b110652ce2ea79b12a37b2d0b9b3db`.

### Следующий шаг

Дождаться полного CI на актуальном head и выполнить squash merge PR #571.
