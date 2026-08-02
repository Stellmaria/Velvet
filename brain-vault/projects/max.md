---
id: project-max
type: project
scope: project-max
status: active
owner: max-coder
sensitivity: internal
version: 1
updated: 2026-08-02
---

# Project context: Romatic Club Max

- Repository: `Stellmaria/romatic_club_bot_max`.
- Workspace: `/workspace` в отдельном coder-container.
- Controller-managed global `AGENTS.md` всегда обязателен.
- Legacy production schema исследуется только read-only ролью `card_hunter`.
- Applied migrations не переписываются; совместимость historical data
  проверяется до constraint или нормализации.
- Изменение завершается focused tests, одним PR и CI evidence.

Файлы, миграции, память и credentials Velvet запрещено переносить в Max.
