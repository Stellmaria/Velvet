from pathlib import Path

root = Path('.')
source = root / 'docs/worklog/2026-07-19-p2af-prompt-result-job-boundary.md'
target = root / 'docs/worklog/2026-07-19-p2ag-formatting-boundaries.md'
text = source.read_text(encoding='utf-8')
changes = [
    ('# Сессия: P2AF', '# Сессия: P2AG'),
    ('2026-07-19-p2af-prompt-result-job-boundary', '2026-07-19-p2ag-formatting-boundaries'),
    ('Velvet Archive, P2AF', 'Velvet Archive, P2AG'),
    ('agent/p2af-prompt-result-job-boundary', 'agent/p2ag-formatting-boundaries'),
    ('5e5d65d9b6af29574eff8a3f410ba4d22c54e010', '9ce21aaccdaecab19c41a0da3639749b38edc3f6'),
    ('Закрепить lifecycle prompt/result AI job.', 'Закрыть source parsing и formatting job boundaries.'),
    ('68 raw, 18 unresolved.', '68 raw, 17 unresolved.'),
    ('Failure компенсируется; session сохраняется; cancellation пробрасывается; CI зелёный.', 'Ожидаемые source errors обрабатываются; неожиданные ошибки и cancellation пробрасываются; AI job компенсирует failure; CI зелёный.'),
    ('Успешный report lifecycle и session cleanup не меняются.', 'Успешный formatting lifecycle и rendering не меняются.'),
    ('Approved 50 → 51; unresolved 18 → 17.', 'Raw 68 → 67; approved 51 → 52; unresolved 17 → 15.'),
    ('PR #182; финальный commit после CI.', 'PR после generation.'),
    ('### Незавершённое\n17 unresolved.', '### Незавершённое\n15 unresolved.'),
    ('### Следующий шаг\n`velvet_bot/handlers/velvet_ai_formatting.py`.', '### Следующий шаг\nПервый AST target.'),
]
for old, new in changes:
    if old not in text:
        raise SystemExit(f'missing template fragment: {old}')
    text = text.replace(old, new)
target.write_text(text, encoding='utf-8')

old_status = '3. P2AF: prompt/result AI jobs compensate failures, preserve retry sessions and cancellation; approved 50 → 51 and unresolved 18 → 17.'
new_status = '3. P2AG: formatting source errors are narrowed and formatting jobs compensate failures; raw 68 → 67, approved 51 → 52, unresolved 17 → 15.'
for relative in ('docs/development_status.md', 'docs/project_memory.md'):
    path = root / relative
    value = path.read_text(encoding='utf-8')
    if old_status not in value:
        raise SystemExit(f'missing P2AF status in {relative}')
    path.write_text(value.replace(old_status, new_status), encoding='utf-8')

changelog = root / 'CHANGELOG.md'
value = changelog.read_text(encoding='utf-8')
marker = '## [Unreleased]\n'
entry = '''\n### P2AG: formatting boundaries\n\n- Formatting source parsing now handles only expected ValueError and RuntimeError failures.\n- Unexpected parsing failures and cancellation propagate unchanged.\n- Formatting AI job failure compensation is verified.\n- Raw broad baseline decreased from 68 to 67; unresolved decreased from 17 to 15.\n'''
if marker not in value:
    raise SystemExit('missing changelog marker')
changelog.write_text(value.replace(marker, marker + entry, 1), encoding='utf-8')
