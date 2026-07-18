# Сессия: Windows hotfix тестов Krita и worker registry

- Дата: 2026-07-18
- ID: `2026-07-18-hotfix-windows-krita-worker-tests`
- Линия/фаза: стабилизация Supervisor/Krita, вне Фазы 18
- Статус: завершено
- Ветка: `agent/hotfix-windows-krita-worker-tests`
- Базовый commit: `d3a3633aad512a44ee19f74711099eb9826a8480`

## Перед началом

### Цель

Исправить два кроссплатформенных тестовых регресса, из-за которых Supervisor `update` откатывается на Windows с Python 3.14 после успешного обновления кода.

### Исходный контекст

- локальный прогон на Windows завершался двумя `TypeError` в `test_krita_process_manager`;
- `_FakeProcess`, подставленный вместо `subprocess.Popen`, перехватывал внутренний `Popen` вызова `subprocess.run()` внутри `_running_krita_pids()`;
- worker registry test наследовал локальный `KRITA_WATERMARK_ENABLED=true` и получал дополнительный `krita-watermark` worker;
- Linux CI не воспроизводил первый дефект, потому что `_running_krita_pids()` не вызывает `tasklist.exe` вне Windows.

### Планируемый объём

1. Изолировать Krita process tests от платформенного `tasklist.exe`, подменяя `_running_krita_pids()` моделью состояния fake managed process.
2. Изолировать worker registry test от локального environment явным `KRITA_WATERMARK_ENABLED=false`.
3. Добавить отдельную проверку включённого watermark worker.
4. Прогнать полный CI и слить отдельным hotfix PR.

### Критерии готовности

- Krita process tests не передают `_FakeProcess` во внутренний `subprocess.run()`;
- worker registry test одинаково проходит при любом локальном значении feature flag;
- отдельно проверены оба режима `KRITA_WATERMARK_ENABLED`;
- полный test suite зелёный;
- production-код не изменён.

### Риски и ограничения

- production-код Supervisor, Krita lifecycle и worker registry не меняются;
- Фаза 18AC остаётся отдельным draft PR;
- Heavy Runtime ТЗ не затрагивается;
- GitHub CI работает на Linux, поэтому исправление Windows-регресса дополнительно подтверждается структурой теста и повторным локальным Supervisor `update` после merge.

## После завершения

### Фактически сделано

- добавлен `_bind_fake_running_pids()`, который моделирует наличие managed Krita только после старта fake process;
- два Krita lifecycle теста больше не зависят от реального `os.name` и Windows `tasklist.exe`;
- worker registry test явно устанавливает `KRITA_WATERMARK_ENABLED=false`;
- добавлен отдельный тест регистрации `krita-watermark` при `KRITA_WATERMARK_ENABLED=true`;
- production-файлы не изменялись.

### Миграции и совместимость

- миграции не изменялись;
- runtime-контракты Supervisor, Krita ownership/idle shutdown и worker registration не изменялись;
- исправление совместимо с Python 3.13 и Python 3.14.

### Проверки

- PR CI `tests #651`, run `29641255441`: 581 функциональный тест прошёл; единственный failure был в project-notes contract из-за неполного worklog;
- diff PR #132 содержит только два test-файла и эту запись;
- после заполнения обязательных разделов требуется финальный повторный CI.

### PR и commit

- PR: #132 `Hotfix: Windows-тесты Krita и изоляция worker registry`;
- test commits: `2815ada601deffd576ccf69f415e415db17d394e`, `057aede5555c62fa0eb2ba8c74d4642d74ac7160`.

### Незавершённое

В коде hotfix незавершённых изменений нет. После merge требуется повторить Supervisor `update` на целевой Windows, чтобы подтвердить устранение исходного Python 3.14 traceback.

### Следующий шаг

После успешного Windows update вернуться к draft PR #131 и продолжить Фазу 18AC.
