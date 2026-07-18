from pathlib import Path

root = Path('.')
source = root / 'docs/worklog/2026-07-19-p2ae-supervisor-console-watcher.md'
target = root / 'docs/worklog/2026-07-19-p2af-prompt-result-job-boundary.md'
text = source.read_text(encoding='utf-8')
changes = [
    ('# Сессия: P2AE', '# Сессия: P2AF'),
    ('2026-07-19-p2ae-supervisor-console-watcher', '2026-07-19-p2af-prompt-result-job-boundary'),
    ('Velvet Archive, P2AE', 'Velvet Archive, P2AF'),
    ('agent/p2ae-supervisor-console-watcher', 'agent/p2af-prompt-result-job-boundary'),
    ('6a4a2128343cfdb912592bc404c441ca4332345c', '5e5d65d9b6af29574eff8a3f410ba4d22c54e010'),
    ('Закрепить boundary фонового watcher.', 'Закрепить lifecycle prompt/result AI job.'),
    ('68 raw, 19 unresolved.', '68 raw, 18 unresolved.'),
    ('Failure логируется и изолируется; cancellation пробрасывается; CI зелёный.', 'Failure компенсируется; session сохраняется; cancellation пробрасывается; CI зелёный.'),
    ('Основной operation lifecycle не меняется.', 'Успешный report lifecycle и session cleanup не меняются.'),
    ('Approved 49 → 50; unresolved 19 → 18.', 'Approved 50 → 51; unresolved 18 → 17.'),
    ('PR #181; финальный commit после CI.', 'PR после generation.'),
    ('### Незавершённое\n18 unresolved.', '### Незавершённое\n17 unresolved.'),
    ('### Следующий шаг\n`velvet_bot/handlers/velvet_ai.py`.', '### Следующий шаг\nПервый AST target.'),
]
for old, new in changes:
    if old not in text:
        raise SystemExit(f'missing template fragment: {old}')
    text = text.replace(old, new)
target.write_text(text, encoding='utf-8')

old_status = '3. P2AE: Supervisor console watcher failure boundary verified; approved 49 → 50 and unresolved 19 → 18.'
new_status = '3. P2AF: prompt/result AI jobs compensate failures, preserve retry sessions and cancellation; approved 50 → 51 and unresolved 18 → 17.'
for relative in ('docs/development_status.md', 'docs/project_memory.md'):
    path = root / relative
    value = path.read_text(encoding='utf-8')
    if old_status not in value:
        raise SystemExit(f'missing P2AE status in {relative}')
    path.write_text(value.replace(old_status, new_status), encoding='utf-8')

changelog = root / 'CHANGELOG.md'
value = changelog.read_text(encoding='utf-8')
marker = '## [Unreleased]\n'
entry = '''\n### P2AF: prompt/result job boundary\n\n- Prompt/result AI job failures now have a verified compensation boundary.\n- Prompt sessions remain available after failure or cancellation for a retry.\n- Compensation persistence failures are not silently swallowed.\n- Unresolved broad baseline decreased from 18 to 17.\n'''
if marker not in value:
    raise SystemExit('missing changelog marker')
changelog.write_text(value.replace(marker, marker + entry, 1), encoding='utf-8')
