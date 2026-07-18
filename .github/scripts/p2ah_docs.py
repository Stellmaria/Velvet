from pathlib import Path

root = Path('.')
source = root / 'docs/worklog/2026-07-19-p2ag-formatting-boundaries.md'
target = root / 'docs/worklog/2026-07-19-p2ah-visual-analysis-job-boundary.md'
text = source.read_text(encoding='utf-8')
changes = [
    ('# Сессия: P2AG', '# Сессия: P2AH'),
    ('2026-07-19-p2ag-formatting-boundaries', '2026-07-19-p2ah-visual-analysis-job-boundary'),
    ('Velvet Archive, P2AG', 'Velvet Archive, P2AH'),
    ('agent/p2ag-formatting-boundaries', 'agent/p2ah-visual-analysis-job-boundary'),
    ('9ce21aaccdaecab19c41a0da3639749b38edc3f6', '7a9091b9a027649225ae37ae38fa485bdb56cbc7'),
    ('Закрыть source parsing и formatting job boundaries.', 'Закрепить lifecycle palette/composition AI job.'),
    ('68 raw, 17 unresolved.', '67 raw, 15 unresolved.'),
    ('Ожидаемые source errors обрабатываются; неожиданные ошибки и cancellation пробрасываются; AI job компенсирует failure; CI зелёный.', 'Failure компенсируется; cancellation пробрасывается; delivery failure не переоткрывает ready job; CI зелёный.'),
    ('Успешный formatting lifecycle и rendering не меняются.', 'Palette extraction, analysis и report rendering не меняются.'),
    ('Raw 68 → 67; approved 51 → 52; unresolved 17 → 15.', 'Approved 52 → 53; unresolved 15 → 14.'),
    ('PR #183; финальный commit после CI.', 'PR после generation.'),
    ('### Незавершённое\n15 unresolved.', '### Незавершённое\n14 unresolved.'),
    ('### Следующий шаг\n`velvet_bot/handlers/velvet_ai_visual.py`.', '### Следующий шаг\nПервый AST target.'),
]
for old, new in changes:
    if old not in text:
        raise SystemExit(f'missing template fragment: {old}')
    text = text.replace(old, new)
target.write_text(text, encoding='utf-8')

old_status = '3. P2AG: formatting source errors are narrowed and formatting jobs compensate failures; raw 68 → 67, approved 51 → 52, unresolved 17 → 15.'
new_status = '3. P2AH: palette/composition AI jobs compensate failures without reopening ready jobs on delivery errors; approved 52 → 53 and unresolved 15 → 14.'
for relative in ('docs/development_status.md', 'docs/project_memory.md'):
    path = root / relative
    value = path.read_text(encoding='utf-8')
    if old_status not in value:
        raise SystemExit(f'missing P2AG status in {relative}')
    path.write_text(value.replace(old_status, new_status), encoding='utf-8')

changelog = root / 'CHANGELOG.md'
value = changelog.read_text(encoding='utf-8')
marker = '## [Unreleased]\n'
entry = '''\n### P2AH: visual analysis job boundary\n\n- Palette/composition AI job failure compensation and cancellation behavior are verified.\n- Palette-card delivery failures occur after the job is ready and do not rewrite its lifecycle.\n- Compensation persistence failures remain visible.\n- Unresolved broad baseline decreased from 15 to 14.\n'''
if marker not in value:
    raise SystemExit('missing changelog marker')
changelog.write_text(value.replace(marker, marker + entry, 1), encoding='utf-8')
