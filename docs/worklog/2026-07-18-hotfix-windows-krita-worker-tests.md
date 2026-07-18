# Сессия: Windows hotfix тестов Krita и worker registry

- Дата: 2026-07-18
- ID: `2026-07-18-hotfix-windows-krita-worker-tests`
- Линия/фаза: стабилизация Supervisor/Krita, вне Фазы 18
- Статус: частично
- Ветка: `agent/hotfix-windows-krita-worker-tests`
- Базовый commit: `d3a3633aad512a44ee19f74711099eb9826a8480`

## Перед началом

### Цель

Исправить два кроссплатформенных тестовых регресса, из-за которых Supervisor `update` откатывается на Windows с Python 3.14 после успешного обновления кода.

### Симптомы

- `_FakeProcess`, подставленный вместо `subprocess.Popen`, перехватывает внутренний `Popen` вызова `subprocess.run()` внутри `_running_krita_pids()` и не поддерживает context manager protocol;
- worker registry test наследует локальный `KRITA_WATERMARK_ENABLED=true` и получает дополнительный `krita-watermark` worker.

### План

1. Изолировать Krita process tests от платформенного `tasklist.exe`, подменяя `_running_krita_pids()` моделью состояния fake managed process.
2. Изолировать worker registry test от локального environment явным `KRITA_WATERMARK_ENABLED=false`.
3. Добавить отдельную проверку включённого watermark worker.
4. Прогнать полный CI и слить отдельным hotfix PR.

### Ограничения

- production-код Supervisor, Krita lifecycle и worker registry не меняются;
- Фаза 18AC остаётся отдельным draft PR;
- Heavy Runtime ТЗ не затрагивается.

## После завершения

Ожидается реализация и CI.
