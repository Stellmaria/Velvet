from pathlib import Path

root = Path('.')
source = root / 'docs/worklog/2026-07-18-p2aa-set-analysis-job-boundaries.md'
target = root / 'docs/worklog/2026-07-19-p2ab-quality-sets-safe-edit.md'
text = source.read_text(encoding='utf-8')
replacements = {
    '# Сессия: P2AA — set analysis jobs': '# Сессия: P2AB — quality sets safe edit',
    '2026-07-18-p2aa-set-analysis-job-boundaries': '2026-07-19-p2ab-quality-sets-safe-edit',
    '- Дата: 2026-07-18': '- Дата: 2026-07-19',
    'Velvet Archive, P2AA': 'Velvet Archive, P2AB',
    'agent/p2aa-set-analysis-job-boundaries': 'agent/p2ab-quality-sets-safe-edit',
    '6235548861b9f7d1ba1dd5cb193fb721a4c41ef0': 'e69e2ada66564db979e02260b72a15578c8d145c',
    'Проверить два lifecycle boundary.': 'Сузить обработку ошибки редактирования.',
    '69 raw, 24 unresolved.': '69 raw, 22 unresolved.',
    'Markers, tests, inventory, документы.': 'Код, tests, inventory, документы.',
    'Failure компенсируется; cancellation пробрасывается; CI зелёный.': 'Точные ошибки и cancellation пробрасываются; CI зелёный.',
    'Анализ сета не меняется.': 'Остальной workflow не меняется.',
    'Две boundaries классифицированы. Baseline 24 → 22.': 'Broad catch удалён. Raw 69 → 68; unresolved 22 → 21.',
    '22 unresolved.': '21 unresolved.',
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f'missing worklog template fragment: {old}')
    text = text.replace(old, new)
target.write_text(text, encoding='utf-8')

old_status = '3. P2AA: set-analysis callback and command jobs compensate failures and preserve cancellation; unresolved broad baseline 24 → 22.'
new_status = '3. P2AB: quality-set safe edit handles only TelegramBadRequest; raw broad baseline 69 → 68 and unresolved 22 → 21.'
for relative in ('docs/development_status.md', 'docs/project_memory.md'):
    path = root / relative
    value = path.read_text(encoding='utf-8')
    if old_status not in value:
        raise SystemExit(f'missing status line in {relative}')
    path.write_text(value.replace(old_status, new_status), encoding='utf-8')

changelog = root / 'CHANGELOG.md'
value = changelog.read_text(encoding='utf-8')
marker = '## [Unreleased]\n'
entry = '''\n### P2AB: quality sets safe edit\n\n- Narrowed quality-set message editing to TelegramBadRequest.\n- Non-Telegram failures and cancellation now propagate unchanged.\n- Raw broad baseline decreased from 69 to 68; unresolved decreased from 22 to 21.\n'''
if marker not in value:
    raise SystemExit('missing changelog marker')
changelog.write_text(value.replace(marker, marker + entry, 1), encoding='utf-8')
