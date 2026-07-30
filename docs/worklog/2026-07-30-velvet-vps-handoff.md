# 2026-07-30 — Velvet VPS production handoff

- Дата: 2026-07-30
- ID: velvet-vps-handoff
- Линия/фаза: hotfix/эксплуатация вне фаз — Linux VPS production migration
- Статус: частично
- Ветка: `main`
- Базовый commit: `db9ad988fbc5f3d3768f35585e2a2d7200a410b1`

## Перед началом

### Цель

Подтвердить готовность существующего Velvet production-контура к переносу на Linux VPS, устранить только обнаруженные deployment-contract blockers и подготовить проверяемый handoff без добавления нового предметного функционала.

### Исходный контекст

В репозитории уже есть отдельный server Compose, preflight, restore drill, smoke script, systemd unit и runbook. Второй Telegram-бот не входит в scope: его deployment-контракт ещё не определён. В рабочей копии обнаружена чужая untracked папка `chapter_analysis_work/`; она не входит в изменения этой сессии.

### Планируемый объём

- проверить Compose, env, preflight, smoke/restore и shell contracts;
- выполнить доступные локальные проверки без секретов и Docker daemon;
- зафиксировать недоступные live проверки как VPS obligations;
- дополнить runbook только при фактически найденной неоднозначности.

### Критерии готовности

- server-контур не включает фиктивный второй бот;
- preflight и deployment tests проходят без раскрытия секретов;
- runbook содержит точный первый запуск, restore, smoke и rollback;
- ограничения локальной Windows-среды явно записаны.

### Риски и ограничения

Docker CLI отсутствует в текущей среде, поэтому build/Compose/restore с реальным PostgreSQL невозможно подтвердить локально. VPS, Telegram token, production dump и provider keys отсутствуют и не будут создаваться или копироваться в рамках этой сессии.

### Стабилизационное обоснование

Изменение улучшает существующую эксплуатацию Velvet: делает перенос, восстановление и контроль запуска воспроизводимыми. Новая предметная область не добавляется; Telegram controllers, repositories и существующие boundaries не расширяются.

## После завершения

Статус: частично.

### Фактически сделано

- Подтверждена граница первого production stack: `docker-compose.server.yml` запускает только Velvet PostgreSQL и Velvet bot; Hermes остаётся optional profile без Docker socket и production data volume.
- Подтверждено намеренное исключение второго Telegram-бота до его собственного repository/start/env/database/backup contract.
- Проверены server Compose, `.env.server.example`, runbook и deployment script; runbook покрывает VPS preparation, final dump, disposable restore drill, first boot без AI, smoke, rollback и постепенное включение AI.
- Добавлена эта handoff-запись с фактическими ограничениями среды.

### Изменённые модули и контракты

- Только `docs/worklog/2026-07-30-velvet-vps-handoff.md`.
- Production code, migrations, Compose и secrets не изменялись.

### Миграции и совместимость

Миграции не изменялись. Контур продолжает использовать существующий packaged PostgreSQL migration/restore workflow.

### Проверки

- `python scripts/server_preflight.py --help` — успешно;
- `python -m compileall -q velvet_bot scripts deploy` — успешно;
- Docker CLI — отсутствует в локальной Windows-среде;
- `.venv` и `.venv314` не содержат pytest, поэтому deployment contract tests здесь не запускались и должны быть подтверждены CI или Docker-enabled VPS.

### PR и commit

Документ подготовлен на `main` относительно базового commit `db9ad988fbc5f3d3768f35585e2a2d7200a410b1`. Production-code commit в рамках этой записи не создавался.

### Незавершённое

- выполнить `pytest` deployment-contract suite в CI/подготовленном dev env;
- на VPS выполнить `docker compose ... config --quiet`, build, restore drill, smoke и owner Telegram smoke по runbook;
- получить второй бот как отдельный deployment contract, не смешивая его с Velvet production stack.

### Следующий шаг

На VPS создать `.env.server` с правами 600, выполнить server preflight и `docker compose config --quiet`, затем сделать restore drill финального dump до первого запуска Velvet без AI.