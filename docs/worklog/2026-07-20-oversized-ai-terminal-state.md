# Сессия: terminal state для oversized AI media

- Дата: 2026-07-20
- ID: `2026-07-20-oversized-ai-terminal-state`
- Линия/фаза: AI vision runtime hotfix
- Статус: `завершено`
- Ветка: `agent/fix-oversized-ai-terminal-state`
- Базовый commit: `f11ee8a38c38e9712e91344cef9263858873f415`

## Перед началом

### Цель

Остановить повторные предупреждения Qwen для Telegram image-documents больше 20 МБ, когда Telegram не создаёт thumbnail, и не объединять разные media ID в одну карточку Error Center.

### Исходный контекст

После oversized preview recovery Telegram иногда возвращал временное сообщение без thumbnail. Внутренний fallback создавал отдельный WARNING, затем semantic и quality workers создавали ещё одно предупреждение. Error Center нормализовал числовые media ID, поэтому разные файлы выглядели как повторы одного инцидента.

### Планируемый объём

- сделать отсутствие thumbnail конечным состоянием одного AI-задания;
- сохранить восстановленный preview в `media_files.preview_file_id`;
- не создавать отдельный WARNING внутри thumbnail recovery;
- добавить в окончательную ошибку устойчивый `media_key=m<id>`;
- проверить отсутствие внутреннего retry loop;
- не изменять отложенный channel analytics controller.

### Критерии готовности

- успешный Telegram thumbnail сохраняется и повторно используется;
- отсутствие thumbnail завершает задание как permanent `skipped` через существующий контракт `file is too big`;
- временное сообщение всегда удаляется;
- разные media ID получают разные fingerprint благодаря `media_key`;
- regression tests, Docker build и project notes contract проходят.

### Риски и ограничения

Cloud Bot API не может скачать исходный файл больше лимита, а Telegram не обязан создавать thumbnail. В таком случае качественный AI-анализ исходника технически невозможен без отдельного локального Bot API или MTProto-клиента. Исправление делает это состояние контролируемым и конечным, а не притворяется, что повтор запроса изменит физику.

## После завершения

### Фактически сделано

- recovered thumbnail сохраняется в `media_files.preview_file_id` как для semantic, так и для quality repository;
- внутренние сообщения recovery переведены с WARNING на INFO;
- если thumbnail отсутствует или не скачивается, создаётся окончательная `VisionAnalysisError` с `file is too big`, `media_key=m<id>` и указанием, что автоматический повтор не требуется;
- существующие AI services распознают сообщение как permanent failure и переводят запись в `skipped`;
- добавлены тесты сохранения preview, отсутствия thumbnail, удаления временного сообщения и разделения fingerprint разных media key.

### Миграции и совместимость

SQL-миграции не требуются. Используется существующее поле `media_files.preview_file_id`. Успешные и уже пропущенные результаты не сбрасываются массово.

### Проверки

- `tests/test_resilient_ai_vision.py` покрывает recovery и terminal no-thumbnail path;
- `tests/test_error_center.py` подтверждает разные fingerprint для `media_key=m56` и `media_key=m83`;
- полный CI запускается на PR этой ветки.

### PR и commit

- PR: #228 `Stop repeated oversized AI media warnings`;
- ветка: `agent/fix-oversized-ai-terminal-state`;
- итоговый merge commit будет указан после успешного CI и слияния.

### Незавершённое

Для полноценного анализа исходников, которым Telegram не выдал thumbnail, потребуется отдельный транспорт загрузки: локальный Telegram Bot API server либо MTProto user client с отдельными credentials. В текущем runtime таких credentials и зависимостей нет.

### Следующий шаг

После зелёного CI слить PR, выполнить Supervisor update и убедиться, что новые oversized media создают максимум одну terminal-запись на анализатор и больше не возвращаются в автоматическую очередь.
