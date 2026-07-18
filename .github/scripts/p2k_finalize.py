import json
from pathlib import Path
p=Path('docs/p2_stability_inventory.json')
d=json.loads(p.read_text(encoding='utf-8'))
u=[x for x in d['broad_exceptions'] if x['classification']=='unresolved']
d['next_slice']={'target':u[0]['path'],'kind':'broad_exception_triage'} if u else None
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
