from pathlib import Path

root = Path('.')
worklog = '''# Сессия: P2AM

- Дата: 2026-07-19
- ID: `2026-07-19-p2am-publication-stability`
- Линия/фаза: Velvet Archive, P2AM
- Статус: завершено
- Ветка: `agent/p2am-publication-stability`
- Базовый commit: `acea7f602a60849aa05f33db4529e5ad736aa89f`

## Перед началом

### Цель
Проверить capture middleware и publication worker.

### Исходный контекст
67 raw, 8 unresolved.

### Планируемый объём
Код, tests, inventory, документы.

### Критерии готовности
Capture failure не блокирует handler; worker восстанавливается; cancellation пробрасывается; CI зелёный.

### Риски и ограничения
Publication domain workflow не меняется.

## После завершения

### Фактически сделано
Approved 59 → 61; unresolved 8 → 6.

### Миграции и совместимость
Без миграций.

### Проверки
Tests, Docker, notes.

### PR и commit
PR после generation.

### Незавершённое
6 unresolved.

### Следующий шаг
Первый AST target.
'''
(root / 'docs/worklog/2026-07-19-p2am-publication-stability.md').write_text(worklog, encoding='utf-8')

new_status = '3. P2AM: publication inbox capture and due-worker iteration failures are isolated while cancellation stays terminal; approved 59 → 61 and unresolved 8 → 6.'
for relative in ('docs/development_status.md', 'docs/project_memory.md'):
    path = root / relative
    lines = path.read_text(encoding='utf-8').splitlines()
    index = next((i for i, line in enumerate(lines) if line.startswith('3. P2AL:')), None)
    if index is None:
        raise SystemExit(f'missing P2AL line in {relative}')
    lines[index] = new_status
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

changelog = root / 'CHANGELOG.md'
value = changelog.read_text(encoding='utf-8')
marker = '## [Unreleased]\n'
entry = '\n### P2AM: publication stability boundaries\n\n- Inbox capture failures no longer block the main Telegram handler.\n- Publication worker iteration failures are logged and followed by another cycle.\n- Cancellation remains terminal on both layers.\n- Unresolved broad baseline decreased from 8 to 6.\n'
if marker not in value:
    raise SystemExit('missing changelog marker')
changelog.write_text(value.replace(marker, marker + entry, 1), encoding='utf-8')
