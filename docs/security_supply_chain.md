# Security и supply chain

## Обязательный CI-контур

`security supply chain` запускается для каждого pull request, каждого push в `main` и вручную. Контур не использует production-секреты и работает с `contents: read`; единственное write-разрешение выдано job CodeQL как `security-events: write`.

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

Security-артефакты содержат только scanner output, generated locks, CycloneDX SBOM и `build-metadata.json`. Запрещено выгружать `.env`, runtime-каталоги, backup, пользовательские медиа, Telegram payloads и application logs. Retention ограничен 7 днями для диагностик и 14 днями для SBOM/provenance.

## Проверенный production-образ

`build-metadata.json` связывает:

- точный source commit;
- локальный OCI image digest (`sha256:...`);
- SHA-256 `requirements.lock`;
- URL workflow run.

Перед production deploy оператор обязан:

1. скачать SBOM/provenance из успешного `image-security` job;
2. проверить, что `source_commit` совпадает с одобренным commit в `main`;
3. проверить SHA-256 локального `requirements.lock`;
4. публиковать образ в registry без пересборки;
5. развернуть образ только по registry digest (`image@sha256:...`), не по mutable tag;
6. приложить digest и workflow run к release/deploy evidence.

Пересборка после успешного scan создаёт другой артефакт и требует нового полного security run.
