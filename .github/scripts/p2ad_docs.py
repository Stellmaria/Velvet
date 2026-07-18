from pathlib import Path

root = Path('.')
source = root / 'docs/worklog/2026-07-19-p2ac-reference-comparison-audit.md'
target = root / 'docs/worklog/2026-07-19-p2ad-reference-form-job-boundary.md'
text = source.read_text(encoding='utf-8')
replacements = {
    '# Сессия: P2AC': '# Сессия: P2AD',
    '2026-07-19-p2ac-reference-comparison-audit': '2026-07-19-p2ad-reference-form-job-boundary',
    'Velvet Archive, P2AC': 'Velvet Archive, P2AD',
    'agent/p2ac-reference-comparison-audit': 'agent/p2ad-reference-form-job-boundary',
    'fa28d8aa012e4405008cbdd742863effe5fca53c': 'e57ed1df91079fe3058514558a3c196c7de756e3',
    'Добавить настоящий audit для ошибки сравнения.': 'Закрепить lifecycle формы сравнения.',
    '68 raw, 21 unresolved.': '68 raw, 20 unresolved.',
    'Ошибка фиксируется; cancellation пробрасывается; CI зелёный.': 'Failure компенсируется; cancellation пробрасывается; CI зелёный.',
    'Успешный путь не меняется.': 'Успешный анализ и формат отчёта не меняются.',
    'Approved 47 → 48; unresolved 21 → 20.': 'Approved 48 → 49; unresolved 20 → 19.',
    'PR #179; финальный commit после CI.': 'PR после generation.',
    '### Незавершённое\n20 unresolved.': '### Незавершённое\n19 unresolved.',
    '### Следующий шаг\n`velvet_bot/handlers/reference_comparison_help.py`.': '### Следующий шаг\nПервый AST target.',
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f'missing worklog template fragment: {old}')
    text = text.replace(old, new)
target.write_text(text, encoding='utf-8')

old_status = '3. P2AC: reference-comparison failures create a real audit incident; approved 47 → 48 and unresolved 21 → 20.'
new_status = '3. P2AD: reference-form AI jobs compensate failures and preserve cancellation; approved 48 → 49 and unresolved 20 → 19.'
for relative in ('docs/development_status.md', 'docs/project_memory.md'):
    path = root / relative
    value = path.read_text(encoding='utf-8')
    if old_status not in value:
        raise SystemExit(f'missing status line in {relative}')
    path.write_text(value.replace(old_status, new_status), encoding='utf-8')

changelog = root / 'CHANGELOG.md'
value = changelog.read_text(encoding='utf-8')
marker = '## [Unreleased]\n'
entry = '''\n### P2AD: reference form job boundary\n\n- Reference-comparison form jobs now have a verified failure-compensation boundary.\n- Cancellation records interruption and propagates unchanged.\n- Compensation persistence failures are not silently swallowed.\n- Unresolved broad baseline decreased from 20 to 19.\n'''
if marker not in value:
    raise SystemExit('missing changelog marker')
changelog.write_text(value.replace(marker, marker + entry, 1), encoding='utf-8')
