from pathlib import Path

root = Path('.')
worklog = '''# Сессия: P2AK

- Дата: 2026-07-19
- ID: `2026-07-19-p2ak-public-notification-boundaries`
- Линия/фаза: Velvet Archive, P2AK
- Статус: завершено
- Ветка: `agent/p2ak-public-notification-boundaries`
- Базовый commit: `125af10d4cbd7936737c68f0724f2493fff2d72e`

## Перед началом

### Цель
Проверить два уровня отправки уведомлений.

### Исходный контекст
67 raw, 12 unresolved.

### Планируемый объём
Код, tests, inventory, документы.

### Критерии готовности
Ошибки изолируются; cancellation пробрасывается; CI зелёный.

### Риски и ограничения
Формат сообщения не меняется.

## После завершения

### Фактически сделано
Approved 55 → 57; unresolved 12 → 10.

### Миграции и совместимость
Без миграций.

### Проверки
Tests, Docker, notes.

### PR и commit
PR после generation.

### Незавершённое
10 unresolved.

### Следующий шаг
Первый AST target.
'''
(root / 'docs/worklog/2026-07-19-p2ak-public-notification-boundaries.md').write_text(worklog, encoding='utf-8')

new_status = '3. P2AK: notification delivery and worker failures are isolated; approved 55 → 57 and unresolved 12 → 10.'
for relative in ('docs/development_status.md', 'docs/project_memory.md'):
    path = root / relative
    lines = path.read_text(encoding='utf-8').splitlines()
    index = next((i for i, line in enumerate(lines) if line.startswith('3. P2AJ:')), None)
    if index is None:
        raise SystemExit(f'missing P2AJ line in {relative}')
    lines[index] = new_status
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

changelog = root / 'CHANGELOG.md'
value = changelog.read_text(encoding='utf-8')
marker = '## [Unreleased]\n'
entry = '\n### P2AK: notification boundaries\n\n- Recipient and worker failures are isolated.\n- Delivery and cancellation contracts are verified.\n- Unresolved broad baseline decreased from 12 to 10.\n'
if marker not in value:
    raise SystemExit('missing changelog marker')
changelog.write_text(value.replace(marker, marker + entry, 1), encoding='utf-8')
