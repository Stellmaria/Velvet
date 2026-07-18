from pathlib import Path

root = Path('.')
source = root / 'docs/worklog/2026-07-19-p2ai-archive-preview-fallback.md'
target = root / 'docs/worklog/2026-07-19-p2aj-media-quality-worker-boundary.md'
text = source.read_text(encoding='utf-8')
changes = [
    ('# Сессия: P2AI', '# Сессия: P2AJ'),
    ('2026-07-19-p2ai-archive-preview-fallback', '2026-07-19-p2aj-media-quality-worker-boundary'),
    ('Velvet Archive, P2AI', 'Velvet Archive, P2AJ'),
    ('agent/p2ai-archive-preview-fallback', 'agent/p2aj-media-quality-worker-boundary'),
    ('b561eda32455cc8c4f1ed64b858c904fc799ac6e', '1044c19866385574ac9c7443004a25b898813306'),
    ('Закрепить full-quality archive preview fallback.', 'Закрепить изоляцию итерации media-quality worker.'),
    ('67 raw, 14 unresolved.', '67 raw, 13 unresolved.'),
    ('Новый cache переиспользуется; legacy cache ремонтируется; failure возвращает fallback; cancellation пробрасывается; CI зелёный.', 'Ошибка одной итерации логируется; следующий цикл выполняется; cancellation пробрасывается; CI зелёный.'),
    ('Archive media persistence и Telegram cache не меняются.', 'Domain service и scheduling interval не меняются.'),
    ('Approved 53 → 54; unresolved 14 → 13.', 'Approved 54 → 55; unresolved 13 → 12.'),
    ('PR #185; финальный commit после CI.', 'PR после generation.'),
    ('### Незавершённое\n13 unresolved.', '### Незавершённое\n12 unresolved.'),
    ('### Следующий шаг\n`velvet_bot/media_quality.py`.', '### Следующий шаг\nПервый AST target.'),
]
for old, new in changes:
    if old not in text:
        raise SystemExit(f'missing template fragment: {old}')
    text = text.replace(old, new, 1)
target.write_text(text, encoding='utf-8')

old_status = '3. P2AI: archive full-quality preview failures fall back safely while cache and cancellation contracts remain intact; approved 53 → 54 and unresolved 14 → 13.'
new_status = '3. P2AJ: media-quality worker iteration failures are logged and isolated while cancellation remains terminal; approved 54 → 55 and unresolved 13 → 12.'
for relative in ('docs/development_status.md', 'docs/project_memory.md'):
    path = root / relative
    value = path.read_text(encoding='utf-8')
    if old_status not in value:
        raise SystemExit(f'missing P2AI status in {relative}')
    path.write_text(value.replace(old_status, new_status), encoding='utf-8')

changelog = root / 'CHANGELOG.md'
value = changelog.read_text(encoding='utf-8')
marker = '## [Unreleased]\n'
entry = '''\n### P2AJ: media quality worker boundary\n\n- A failed media-quality iteration is logged and the following cycle still runs.\n- Cancellation remains terminal and is not logged as an iteration failure.\n- Unresolved broad baseline decreased from 13 to 12.\n'''
if marker not in value:
    raise SystemExit('missing changelog marker')
changelog.write_text(value.replace(marker, marker + entry, 1), encoding='utf-8')
