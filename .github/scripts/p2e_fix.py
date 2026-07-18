from pathlib import Path
for n in ('ai_quality.py','ai_vision.py','calibrated_ai_quality.py'):
 p=Path('velvet_bot')/n;t=p.read_text();p.write_text(t.replace('broad-boundary:','p2-approved-boundary:',1))
