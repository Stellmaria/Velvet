# Ускорение Docker-сборки Krita

- Дата: 2026-08-04
- ID: `krita-build-acceleration-2026-08-04`
- Линия/фаза: CI и supply-chain reliability
- Статус: `частично`
- Ветка: `ci/597-accelerate-krita-builds`
- Базовый commit: `5b8b47293213b7ad63b47114368e002e0eb7c7bf`

## Перед началом

### Цель

Сократить время обязательного Docker CI для реальных изменений Krita. После #596 unrelated PR больше не собирает Krita, но Krita-related PR по-прежнему может выполнять холодный `apt-get install krita` из `ubuntu:24.04` и занимать до 40 минут.

### Исходный контекст

`Dockerfile.krita-server` уже расположен корректно с точки зрения layer invalidation: тяжёлый `apt-get install` выполняется до всех repository `COPY`. Поэтому изменения plugin, entrypoint или healthcheck не должны пересобирать системный слой, если BuildKit может его восстановить.

PR #596 добавил `type=gha,scope=velvet-krita`, однако cache, созданный только в feature branch, не является надёжной общей основой для следующих PR. Default branch не прогревает этот scope, если merge не затрагивает Krita surface. В результате новый Krita-related PR всё ещё может начать с пустого cache и снова устанавливать весь графический стек.

Отдельный GHCR base image рассматривался, но признан избыточным для текущей задачи: он добавил бы registry publishing, version/digest lifecycle и новые supply-chain permissions, хотя Dockerfile уже имеет правильную границу тяжёлого слоя.

### Планируемый объём

1. Добавить отдельный workflow прогрева cache только для `main`, schedule и ручного запуска.
2. Использовать тот же `type=gha,scope=velvet-krita`, который читает PR Docker build.
3. Не давать workflow `packages: write` и не публиковать registry image.
4. Дважды в неделю обновлять доступность default-branch cache, чтобы он не исчезал из-за неиспользования.
5. Проверять, что системный package layer остаётся до repository `COPY`.
6. Проверять собранный image через `docker image inspect` и наличие `krita`/`python3` без запуска сервиса.
7. Сохранить существующий полный Krita smoke в PR Docker workflow.
8. Добавить regression contract для triggers, permissions, cache scope, timeout и layer ordering.

### Критерии готовности

- cache warmer не запускается из `pull_request`;
- workflow работает только в доверенном default-branch/scheduled/manual контексте;
- permissions остаются `contents: read` без registry write;
- cache warmer и PR build используют одинаковый `scope=velvet-krita`;
- тяжёлый package layer остаётся до первого repository `COPY`;
- workflow имеет concurrency cancellation и bounded timeout;
- после merge workflow self-trigger прогревает default-branch cache;
- полный CI проходит на актуальном `main`.

### Риски и ограничения

- первый default-branch warm после merge всё ещё может быть холодным и занять значительное время, но он не блокирует pull request;
- редкое изменение самого package layer закономерно потребует полной установки один раз;
- доступность cache зависит от GitHub Actions cache backend, поэтому PR build сохраняет обычный корректный fallback, а не становится cache-only;
- production rollout и `KRITA_SERVER_IMAGE` не меняются;
- Krita smoke и security checks не ослабляются;
- плавающий registry image и дополнительные package permissions не вводятся.

## После завершения

### Фактически сделано

- открыт draft PR #599;
- добавлен `.github/workflows/krita-cache-warm.yml`;
- workflow запускается на `main` при изменениях Krita inputs, дважды в неделю и вручную;
- добавлены read-only permissions, concurrency cancellation и timeout 35 минут;
- cache warmer использует общий `type=gha,scope=velvet-krita` без registry push;
- перед build проверяется порядок package layer и repository `COPY`;
- после build проверяются локальный image и наличие Krita/Python;
- добавлен `tests/test_krita_cache_workflow_contract.py`.

### Миграции и совместимость

Миграций БД и production config нет. `Dockerfile.krita-server`, compose и runtime image contract не меняются. Новый workflow только заполняет уже используемый GHA cache scope. При отсутствии cache PR build продолжает обычную полную сборку.

### Проверки

Добавлены контракты:

- отсутствие `pull_request` trigger;
- default-branch, schedule и manual triggers;
- `contents: read` без `packages: write`, `--push` и GHCR;
- одинаковые cache-from/cache-to scope в warmer и PR build;
- timeout и stale-run cancellation;
- package layer до repository copies;
- self-trigger после merge;
- локальная проверка warmed image.

Полный CI PR #599 выполняется. Первый project-notes run выявил только отсутствующие стандартные разделы worklog; содержание приведено к контракту этим commit.

### PR и commit

PR: #599 `Ускорить реальные Docker-сборки Krita`.

Текущий head фиксируется после завершения реализации и зелёного CI.

### Незавершённое

- полный CI ещё не завершён;
- cache warmer ещё не выполнялся на `main`;
- фактическое время первого тёплого Krita-related PR ещё не измерено;
- Docker workflow path/selector contracts требуют финальной сверки.

### Следующий шаг

Довести CI contracts до зелёного состояния, проверить security workflow и итоговый diff. После review и merge дождаться успешного default-branch cache warm, затем измерить реальный Krita-related PR build и подтвердить, что тяжёлый `apt-get install` восстанавливается из cache.
