# Security и supply chain

## Обязательный CI-контур

`security supply chain` запускается для каждого pull request, каждого push в `main` и вручную. Контур не использует production-секреты и работает с `contents: read`; единственное write-разрешение в PR выдано job CodeQL как `security-events: write`.

Проверки разделены на четыре независимых слоя:

1. **Supply-chain contract** проверяет immutable SHA для всех Actions, явные permissions, bounded retention артефактов, реестр исключений и отсутствие drift между входными requirements и hash-locked графом.
2. **Static security** ставит инструменты только из `requirements-dev.lock`, запускает Bandit и ShellCheck на изменённой поверхности, проверяет секреты, Docker/Compose boundary и выполняет `pip-audit` production-графа.
3. **CodeQL** анализирует Python и GitHub Actions с набором `security-extended`.
4. **Image security** собирает production-образ из `requirements.lock`, блокирует High/Critical findings Trivy, создаёт CycloneDX SBOM и сохраняет provenance.

## Канонический dependency graph

Входные файлы:

- `requirements.txt` для production;
- `requirements-dev.txt` для CI и разработки.

Канонические lock-файлы:

- `requirements.lock`;
- `requirements-dev.lock`.

Каждая транзитивная зависимость закреплена версией и SHA-256. CI и production Dockerfile устанавливают зависимости только с `--require-hashes`; повторное разрешение графа при установке запрещено.

Обновление зависимостей выполняется отдельным PR:

```bash
uv pip compile requirements.txt \
  --python-version 3.13 \
  --generate-hashes \
  --no-annotate \
  --no-header \
  --output-file requirements.lock
uv pip compile requirements-dev.txt \
  --python-version 3.13 \
  --generate-hashes \
  --no-annotate \
  --no-header \
  --output-file requirements-dev.lock
python scripts/security_gate.py all
pip-audit --requirement requirements.lock --progress-spinner off --strict
```

Dependabot создаёт раздельные PR для GitHub Actions, Python и Docker. PR обязан содержать обновлённые lock-файлы и проходить полный security workflow.

## Vulnerability policy

- Любая найденная production-зависимость блокирует merge через `pip-audit`.
- High/Critical finding в production-образе блокирует merge через Trivy.
- Неисправленные findings игнорируются image scanner только когда у upstream отсутствует исправление; риск всё равно должен быть отражён в issue и устранён заменой base image или компонента при первой возможности.
- Намеренно уязвимая зависимость хранится только в `tests/fixtures/security/vulnerable-requirements.txt`. CI доказывает, что scanner её обнаруживает и что она не попала в production lock.

## Исключения

Исключения хранятся в `.github/security-exceptions.json`. Каждая запись обязана содержать:

- уникальный `id`;
- ответственного `owner`;
- конкретную причину `reason`;
- дату истечения `expires`;
- regression test или проверку `test_reference`;
- источник finding `source`.

Просроченная или неполная запись ломает CI. Emergency exception допускается максимум на 7 календарных дней и только отдельным reviewable PR с issue на устранение. Бессрочные suppressions запрещены.

## Secret scanning

CI проверяет изменённые файлы на private keys, GitHub/AWS/Telegram credentials и длинные присвоенные секреты. Тестовый fake secret из `tests/fixtures/security/fake-secret.txt` сканируется отдельным regression test и исключён из обычного repository scan.

В настройках публичного репозитория должны оставаться включены GitHub secret scanning и push protection. CI не заменяет push protection: он является вторым независимым барьером.

## Артефакты и приватные данные

Security-артефакты содержат только scanner output, generated locks, CycloneDX SBOM и JSON provenance. Запрещено выгружать `.env`, runtime-каталоги, backup, пользовательские медиа, Telegram payloads и application logs. Retention ограничен 7 днями для диагностик, 14 днями для PR SBOM/provenance и 30 днями для опубликованного production evidence.

## Проверенный production-образ

После merge workflow `publish verified image`:

1. собирает `ghcr.io/stellmaria/velvet:<source commit>` из `requirements.lock`;
2. записывает OCI label `org.opencontainers.image.revision=<source commit>`;
3. блокирует High/Critical findings до публикации;
4. создаёт CycloneDX SBOM;
5. публикует просканированный образ в GHCR;
6. сохраняет `published-image-metadata.json` с source commit, registry digest, SHA-256 lock-файла и URL workflow run.

Production deploy запускается только вручную из `main` через `deploy production`. Обязательные параметры:

- `confirmation=DEPLOY`;
- `source_commit` из `published-image-metadata.json`;
- полный `image_digest` вида `ghcr.io/stellmaria/velvet@sha256:<64 hex>`.

Workflow отклоняет commit, не совпадающий с commit текущего `main`. Remote deploy дополнительно:

1. pull-ит образ только по digest;
2. сверяет OCI revision с target commit;
3. запускает Compose без пересборки bot image;
4. сверяет image ID запущенного контейнера с полученным digest image;
5. выполняет существующий application smoke и rollback при ошибке.

Mutable tags и пересборка bot image во время обычного production deploy запрещены. Локальная сборка остаётся только аварийным rollback fallback, когда verified digest явно не передан вне стандартного CD workflow.
