from pathlib import Path
r=Path(__file__).resolve().parents[2]
old='3. P2D: media-quality claimed-scan compensation boundary классифицирован; unresolved broad baseline 68 → 67.'
new='3. P2E: AI worker boundaries классифицированы; unresolved broad baseline 67 → 64.'
for name in ('development_status.md','project_memory.md'):
 p=r/'docs'/name
 t=p.read_text(encoding='utf-8')
 if old not in t: raise SystemExit(name)
 p.write_text(t.replace(old,new,1),encoding='utf-8')
p=r/'docs/worklog/2026-07-18-p2e-ai-worker-boundaries.md'
t=p.read_text(encoding='utf-8')
p.write_text(t.replace('PR создаётся после runner; номер фиксируется финальным connector-коммитом.','PR #152. Финальный merge выполняется после зелёного CI.'),encoding='utf-8')
