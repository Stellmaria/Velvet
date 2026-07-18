from pathlib import Path

root = Path('.')
source = root / 'docs/worklog/2026-07-19-p2ab-quality-sets-safe-edit.md'
target = root / 'docs/worklog/2026-07-19-p2ac-reference-comparison-audit.md'
text = source.read_text(encoding='utf-8')
replacements = {
    '# Сессия: P2AB — quality sets safe edit': '# Сессия: P2AC — reference comparison audit',
    '2026-07-19-p2ab-quality-sets-safe-edit': '2026-07-19-p2ac-reference-comparison-audit',
    'Velvet Archive, P2AB': 'Velvet Archive, P2AC',
    'agent/p2ab-quality-sets-safe-edit': 'agent/p2ac-reference-comparison-audit',
    'e69e2ada66564db979e02260b72a15578c8d145c': 'fa28d8aa012e4405008cbdd742863effe5fca53c',
    'Сузить обработку ошибки редактирования.': 'Добавить реальный incident audit для ошибки сравнения.',
    '69 raw, 22 unresolved.': '68 raw, 21 unresolved.',
    'Код, tests, inventory, документы.': 'Audit boundary, tests, inventory, документы.',
    'Точные ошибки и cancellation пробрасываются; CI зелёный.': 'Ошибка аудируется; status обновляется; cancellation пробрасывается; CI зелёный.',
    'Остальной workflow не меняется.': 'Успешное сравнение и формат отчёта не меняются.',
    'Broad catch удалён. Raw 69 → 68; unresolved 22 → 21.': 'Boundary аудирована. Approved 47 → 48; unresolved 21 → 20.',
    'PR #178; финальный commit после CI.': 'PR после generation.',
    '21 unresolved.': '20 unresolved.',
    '`velvet_bot/handlers/reference_comparison.py`.': 'Первый AST target.',
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f'missing worklog template fragment: {old}')
    text = text.replace(old, new)
target.write_text(text, encoding='utf-8')

old_status = '3. P2AB: quality-set safe edit handles only TelegramBadRequest; raw broad baseline 69 → 68 and unresolved 22 → 21.'
new_status = '3. P2AC: reference-comparison failures create a real audit incident; approved 47 → 48 and unresolved 21 → 20.'
for relative in ('docs/development_status.md', 'docs/project_memory.md'):
    path = root / relative
    value = path.read_text(encoding='utf-8')
    if old_status not in value:
        raise SystemExit(f'missing status line in {relative}')
    path.write_text(value.replace(old_status, new_status), encoding='utf-8')

changelog = root / 'CHANGELOG.md'
value = changelog.read_text(encoding='utf-8')
marker = '## [Unreleased]\n'
entry = '''\n### P2AC: reference comparison audit\n\n- Reference-comparison failures now create a real Telegram audit incident with character, reference, result, and user context.\n- User-facing failure status remains available when the audit logger is disabled.\n- Cancellation continues to propagate without creating a false incident.\n- Unresolved broad baseline decreased from 21 to 20.\n'''
if marker not in value:
    raise SystemExit('missing changelog marker')
changelog.write_text(value.replace(marker, marker + entry, 1), encoding='utf-8')
