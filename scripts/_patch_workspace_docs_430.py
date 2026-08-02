from __future__ import annotations

import re
from pathlib import Path


requirements = Path("docs/requirements/workspace_product.md")
source = requirements.read_text(encoding="utf-8")
replacement = """## 14. Текущий технический срез

Реализованы и покрыты regression contracts:

- grants и приватное создание personal workspace;
- публичный выбор workspace и tenant-scoped archive callbacks;
- allowed/enabled module policy и отдельная справка;
- workspace categories, universes, stories и идемпотентный импорт КР;
- inline character taxonomy pickers и primary story links;
- workspace-scoped references, publications и analytics;
- owner/admin/editor/reviewer/viewer roles и member dashboard;
- first-run onboarding, Telegram admin-right checks, forum topics и destinations;
- media batch UX, независимые download audience/variant, preserved original и rework visibility;
- PostgreSQL isolation tests, restore drill, type check, Docker и generated inventories.

Полная матрица evidence и tests хранится в
`docs/audits/workspace_product_gap_audit.md` и проверяется
`scripts/audit_workspace_product.py`.

---

## 15. Следующий этап

Первоначальный этап перевода character taxonomy, references, publications,
analytics и team routes на workspace scope завершён. Он больше не является
открытым backlog канонического ТЗ.

Актуальные follow-up разделены по типу:

- `#561` — live owner/onboarding/destinations smoke, bounded slice `#410`;
- `#562` — live role matrix и tenant callback isolation, bounded slice `#410`;
- `#563` — provider-neutral personal quality, bounded code slice `#417`;
- `#426` — video/animation subscriber notifications.

Зелёный CI подтверждает code contracts, но не закрывает live Telegram acceptance.

---

## 16."""
pattern = re.compile(
    r"## 14\. Текущий технический срез\n.*?\n---\n\n"
    r"## 15\. Следующий этап\n.*?\n---\n\n## 16\.",
    re.DOTALL,
)
source, count = pattern.subn(replacement, source, count=1)
if count != 1:
    raise SystemExit("Workspace requirements sections 14-15 were not found")
requirements.write_text(source, encoding="utf-8")

readme = Path("README.md")
source = readme.read_text(encoding="utf-8")
marker = "### Публикации и аналитика\n"
section = """### Личные пространства

- personal workspace создаётся только по grant Стэл и приватен по умолчанию;
- taxonomy, characters, references, publications, analytics, team roles и media controls изолированы по `workspace_id`;
- first-run wizard проверяет права Telegram-бота и сохраняет chat/topic destinations;
- обязательный product contract: `docs/requirements/workspace_product.md`;
- воспроизводимый status/gap audit: `docs/audits/workspace_product_gap_audit.md`.

Live Telegram acceptance ведётся отдельно в `#561` и `#562`; provider-neutral
personal quality и video/animation notifications остаются extensions `#563` и
`#426`, а не скрытыми условиями готовности core workspace.

"""
if "### Личные пространства\n" not in source:
    if marker not in source:
        raise SystemExit("README insertion marker was not found")
    source = source.replace(marker, section + marker, 1)
    readme.write_text(source, encoding="utf-8")
