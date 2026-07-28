# Сессия: регистрация pose extraction AI job

- Дата: 2026-07-28
- ID: `2026-07-28-pose-ai-job-kind-hotfix`
- Линия/фаза: Velvet AI / pose extractor hotfix
- Статус: `завершено`
- Ветка: `agent/fix-pose-ai-job-kind`
- Базовый commit: `b65b46e108b86a4cef348e3d243fa7aa79d7abe2`

## Перед началом

### Цель

Исправить падение операции `Поза → промт` с ошибкой `Неизвестный тип AI-задания`.

### Исходный контекст

Контроллер pose extractor создавал AI job с kind `pose_extraction`, но этот kind не был добавлен в центральный allowlist `AI_JOB_KINDS`. Репозиторий отклонял задание до обращения к PostgreSQL и до запуска Ollama.

### Планируемый объём

- зарегистрировать `pose_extraction` в `AI_JOB_KINDS`;
- добавить regression-тест центрального реестра;
- подтвердить отсутствие миграций базы данных;
- прогнать обязательные проверки CI.

### Критерии готовности

- `AIJobRepository.create(kind="pose_extraction", ...)` проходит валидацию;
- неизвестные kind по-прежнему отклоняются;
- тест явно защищает регистрацию pose extractor;
- обязательные CI-проверки проходят.

### Риски и ограничения

Hotfix не меняет локальную конфигурацию `.env` и не исправляет недоступность Ollama. Старая HF-модель в логах требует отдельного изменения `AI_VISION_MODEL` на целевой Windows-машине.

## После завершения

### Фактически сделано

- `pose_extraction` добавлен в центральный `AI_JOB_KINDS`;
- добавлен тест `test_pose_extraction_is_registered`;
- логика Telegram-контроллера и схема базы данных не изменялись.

### Миграции и совместимость

Миграции не требуются: колонка `ai_jobs.kind` уже хранит строковые значения, а ограничение существовало только в Python allowlist.

### Проверки

Добавлен unit regression-тест. Полный tests workflow, type check, Docker build и project notes contract запускаются в PR.

### PR и commit

Ветка `agent/fix-pose-ai-job-kind`; PR создаётся после записи изменений.

### Незавершённое

На production необходимо обновить `main`, перезапустить Supervisor и отдельно заменить старую HF-модель в `.env` на доступную Ollama vision-модель.

### Следующий шаг

После зелёного CI слить hotfix, обновить Windows checkout и повторить `Qwen → Поза → промт`.
