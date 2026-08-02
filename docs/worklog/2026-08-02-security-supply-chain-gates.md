# Security и supply-chain gates

- Дата: 2026-08-02
- ID: VELVET-512
- Линия/фаза: Линия A / CI и production hardening
- Статус: `частично`
- Ветка: `security/supply-chain-gates-512`
- Базовый commit: `f03ce8885d5cc407b2cc1c422fafbc38b195ad3f`

## Перед началом

### Цель

Закрыть issue #512 единым проверяемым security-контуром: immutable GitHub Actions, воспроизводимые dependency locks, vulnerability/static/secret scanning, SBOM, provenance и digest-based deploy policy.

### Исходный контекст

На базовом commit direct dependencies были закреплены только версиями, CI и production image выполняли установку из `requirements*.txt`, а часть Actions использовала mutable major tags. Отдельных CodeQL, dependency audit, image scan, SBOM и time-limited exception registry не было.

### Планируемый объём

- добавить hash-locked runtime/dev графы и strict install;
- закрепить все Actions полными commit SHA;
- добавить Dependabot для Actions, Python и Docker;
- добавить repository contract, regression fixtures и layered security workflow;
- добавить CodeQL для Python и Actions;
- добавить Trivy image gate, CycloneDX SBOM и provenance;
- описать vulnerability, exception, artifact и digest deployment policy.

### Критерии готовности

- CI воспроизводит lock-файлы и запрещает drift;
- floating Action и dependency без hash ломают тест;
- fake secret и vulnerable fixture обнаруживаются;
- PR/main workflow не используют production secrets;
- High/Critical image findings и dependency findings блокируют merge;
- успешный build сохраняет source commit, image digest и lock digest;
- все обязательные checks зелёные, PR слит в `main`, issue закрыта.

### Риски и ограничения

Lock-файлы должны быть сгенерированы реальным resolver в GitHub-hosted runner, а не составлены вручную. Existing security debt не должен маскироваться бессрочными suppressions; допустимы только видимые исключения с owner, reason, expiry и test reference.

## После завершения

### Фактически сделано

Добавлен первый слой security contract, self-bootstrapping lock workflow, Dependabot, regression fixtures, документация и реестр исключений. Остальные workflow/Dockerfile и сгенерированные lock-файлы будут зафиксированы после получения resolver artifact.

### Миграции и совместимость

Миграций БД нет. Runtime dependency versions не меняются намеренно; меняется способ фиксации и установки полного транзитивного графа.

### Проверки

- GitHub Actions lock generation: ожидается;
- unit/contract tests: ожидаются;
- CodeQL Python/Actions: ожидается;
- pip-audit/Bandit/ShellCheck/secret/container scans: ожидаются;
- Docker build/Trivy/SBOM: ожидаются.

### PR и commit

PR будет создан после bootstrap-коммитов; итоговый merge commit и ссылка будут добавлены перед merge.

### Незавершённое

Получить generated lock artifact, закрепить его в ветке, перевести existing workflows и Dockerfile на strict lock, пройти CI, устранить findings и выполнить merge.

### Следующий шаг

Открыть draft PR для запуска resolver job, скачать generated locks и продолжить hardening в той же ветке.
