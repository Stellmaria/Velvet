from pathlib import Path

root = Path('.')
worklog = '''# Сессия: P2AL

- Дата: 2026-07-19
- ID: `2026-07-19-p2al-public-archive-display-fallbacks`
- Линия/фаза: Velvet Archive, P2AL
- Статус: завершено
- Ветка: `agent/p2al-public-archive-display-fallbacks`
- Базовый commit: `40716e995265385b8d9cad0853f2a86575338b04`

## Перед началом

### Цель
Проверить два preview fallback публичного архива.

### Исходный контекст
67 raw, 10 unresolved.

### Планируемый объём
Код, tests, inventory, документы.

### Критерии готовности
Исходный документ и metadata сохраняются; cancellation пробрасывается; CI зелёный.

### Риски и ограничения
Навигация и public state не меняются.

## После завершения

### Фактически сделано
Approved 57 → 59; unresolved 10 → 8.

### Миграции и совместимость
Без миграций.

### Проверки
Tests, Docker, notes.

### PR и commit
PR после generation.

### Незавершённое
8 unresolved.

### Следующий шаг
Первый AST target.
'''
(root / 'docs/worklog/2026-07-19-p2al-public-archive-display-fallbacks.md').write_text(worklog, encoding='utf-8')

new_status = '3. P2AL: public archive display preview failures fall back to original documents while preserving metadata and cancellation; approved 57 → 59 and unresolved 10 → 8.'
for relative in ('docs/development_status.md', 'docs/project_memory.md'):
    path = root / relative
    lines = path.read_text(encoding='utf-8').splitlines()
    index = next((i for i, line in enumerate(lines) if line.startswith('3. P2AK:')), None)
    if index is None:
        raise SystemExit(f'missing P2AK line in {relative}')
    lines[index] = new_status
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

changelog = root / 'CHANGELOG.md'
value = changelog.read_text(encoding='utf-8')
marker = '## [Unreleased]\n'
entry = '\n### P2AL: public archive display fallbacks\n\n- Viewer edit and send preview failures fall back to original documents.\n- Caption, keyboard, spoiler, and cancellation contracts are verified.\n- Unresolved broad baseline decreased from 10 to 8.\n'
if marker not in value:
    raise SystemExit('missing changelog marker')
changelog.write_text(value.replace(marker, marker + entry, 1), encoding='utf-8')
