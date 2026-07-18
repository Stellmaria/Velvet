from pathlib import Path

root = Path('.')
status = '3. P2AN: media save failure boundaries verified; approved 61 → 63 and unresolved 6 → 4.'
for name in ('docs/development_status.md', 'docs/project_memory.md'):
    path = root / name
    lines = path.read_text(encoding='utf-8').splitlines()
    index = next((i for i, line in enumerate(lines) if line.startswith('3. P2AM:')), None)
    if index is None:
        raise SystemExit(f'missing P2AM line in {name}')
    lines[index] = status
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

path = root / 'CHANGELOG.md'
value = path.read_text(encoding='utf-8')
marker = '## [Unreleased]\n'
entry = '\n### P2AN: media save boundaries\n\n- Save failures are isolated and recorded.\n- Cancellation propagates unchanged.\n- Unresolved broad baseline decreased from 6 to 4.\n'
if marker not in value:
    raise SystemExit('missing changelog marker')
path.write_text(value.replace(marker, marker + entry, 1), encoding='utf-8')
