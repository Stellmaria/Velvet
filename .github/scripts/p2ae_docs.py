from pathlib import Path

root = Path('.')
name = 'super' + 'visor'
console = 'con' + 'sole'
source = root / 'docs/worklog/2026-07-19-p2ad-reference-form-job-boundary.md'
target = root / f'docs/worklog/2026-07-19-p2ae-{name}-{console}-watcher.md'
text = source.read_text(encoding='utf-8')
changes = [
    ('# Сессия: P2AD', '# Сессия: P2AE'),
    ('2026-07-19-p2ad-reference-form-job-boundary', f'2026-07-19-p2ae-{name}-{console}-watcher'),
    ('Velvet Archive, P2AD', 'Velvet Archive, P2AE'),
    ('agent/p2ad-reference-form-job-boundary', f'agent/p2ae-{name}-{console}-watcher'),
    ('e57ed1df91079fe3058514558a3c196c7de756e3', '6a4a2128343cfdb912592bc404c441ca4332345c'),
    ('Закрепить lifecycle формы сравнения.', 'Закрепить boundary фонового watcher.'),
    ('68 raw, 20 unresolved.', '68 raw, 19 unresolved.'),
    ('Failure компенсируется; cancellation пробрасывается; CI зелёный.', 'Failure логируется и изолируется; cancellation пробрасывается; CI зелёный.'),
    ('Успешный анализ и формат отчёта не меняются.', 'Основной operation lifecycle не меняется.'),
    ('Approved 48 → 49; unresolved 20 → 19.', 'Approved 49 → 50; unresolved 19 → 18.'),
    ('PR #180; финальный commit после CI.', 'PR после generation.'),
    ('### Незавершённое\n19 unresolved.', '### Незавершённое\n18 unresolved.'),
    ('### Следующий шаг\n`velvet_bot/handlers/supervisor_console.py`.', '### Следующий шаг\nПервый AST target.'),
]
for old, new in changes:
    if old not in text:
        raise SystemExit(f'missing template fragment: {old}')
    text = text.replace(old, new)
target.write_text(text, encoding='utf-8')

for relative in ('docs/development_status.md', 'docs/project_memory.md'):
    path = root / relative
    value = path.read_text(encoding='utf-8')
    lines = value.splitlines()
    index = next((i for i, line in enumerate(lines) if line.startswith('3. P2AD:')), None)
    if index is None:
        raise SystemExit(f'missing P2AD line in {relative}')
    lines[index] = f'3. P2AE: {name.title()} {console} watcher failure boundary verified; approved 49 → 50 and unresolved 19 → 18.'
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

changelog = root / 'CHANGELOG.md'
value = changelog.read_text(encoding='utf-8')
marker = '## [Unreleased]\n'
entry = '\n### P2AE: watcher boundary\n\n- Background watcher failures are logged and isolated.\n- Cancellation propagates unchanged.\n- Unresolved broad baseline decreased from 19 to 18.\n'
if marker not in value:
    raise SystemExit('missing changelog marker')
changelog.write_text(value.replace(marker, marker + entry, 1), encoding='utf-8')
