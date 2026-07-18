from pathlib import Path

root = Path('.')
source = root / 'docs/worklog/2026-07-19-p2ah-visual-analysis-job-boundary.md'
target = root / 'docs/worklog/2026-07-19-p2ai-archive-preview-fallback.md'
text = source.read_text(encoding='utf-8')
changes = [
    ('# Сессия: P2AH', '# Сессия: P2AI'),
    ('2026-07-19-p2ah-visual-analysis-job-boundary', '2026-07-19-p2ai-archive-preview-fallback'),
    ('Velvet Archive, P2AH', 'Velvet Archive, P2AI'),
    ('agent/p2ah-visual-analysis-job-boundary', 'agent/p2ai-archive-preview-fallback'),
    ('7a9091b9a027649225ae37ae38fa485bdb56cbc7', 'b561eda32455cc8c4f1ed64b858c904fc799ac6e'),
    ('Закрепить lifecycle palette/composition AI job.', 'Закрепить full-quality archive preview fallback.'),
    ('67 raw, 15 unresolved.', '67 raw, 14 unresolved.'),
    ('Failure компенсируется; cancellation пробрасывается; delivery failure не переоткрывает ready job; CI зелёный.', 'Новый cache переиспользуется; legacy cache ремонтируется; failure возвращает fallback; cancellation пробрасывается; CI зелёный.'),
    ('Palette extraction, analysis и report rendering не меняются.', 'Archive media persistence и Telegram cache не меняются.'),
    ('Approved 52 → 53; unresolved 15 → 14.', 'Approved 53 → 54; unresolved 14 → 13.'),
    ('PR после generation.', 'PR после generation.'),
    ('### Незавершённое\n14 unresolved.', '### Незавершённое\n13 unresolved.'),
    ('### Следующий шаг\nПервый AST target.', '### Следующий шаг\nПервый AST target.'),
]
for old, new in changes:
    if old not in text:
        raise SystemExit(f'missing template fragment: {old}')
    text = text.replace(old, new, 1)
target.write_text(text, encoding='utf-8')

old_status = '3. P2AH: palette/composition AI jobs compensate failures without reopening ready jobs on delivery errors; approved 52 → 53 and unresolved 15 → 14.'
new_status = '3. P2AI: archive full-quality preview failures fall back safely while cache and cancellation contracts remain intact; approved 53 → 54 and unresolved 14 → 13.'
for relative in ('docs/development_status.md', 'docs/project_memory.md'):
    path = root / relative
    value = path.read_text(encoding='utf-8')
    if old_status not in value:
        raise SystemExit(f'missing P2AH status in {relative}')
    path.write_text(value.replace(old_status, new_status), encoding='utf-8')

changelog = root / 'CHANGELOG.md'
value = changelog.read_text(encoding='utf-8')
marker = '## [Unreleased]\n'
entry = '''\n### P2AI: archive preview fallback\n\n- Full-quality archive preview failures now have a verified document fallback boundary.\n- New cache records are reused while legacy thumbnail records rebuild themselves.\n- Oversized documents skip Bot API download and cancellation propagates unchanged.\n- Unresolved broad baseline decreased from 14 to 13.\n'''
if marker not in value:
    raise SystemExit('missing changelog marker')
changelog.write_text(value.replace(marker, marker + entry, 1), encoding='utf-8')
