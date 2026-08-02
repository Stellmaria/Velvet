---
id: project-velvet
type: project
scope: project-velvet
status: active
owner: velvet-coder
sensitivity: internal
version: 1
updated: 2026-08-02
---

# Project context: Velvet

- Repository: `Stellmaria/Velvet`.
- Workspace: `/workspace` в отдельном coder-container.
- Канонические инструкции: repository `AGENTS.md`, `docs/project_memory.md`,
  `docs/development_status.md`, stabilization policy и текущий worklog.
- Production checkout не является coder workspace.
- Production PostgreSQL для кодера только read-only.
- Изменение завершается focused tests, project notes, одним PR и CI evidence.

Не инжектируй в prompt всю историю проекта. Сначала используй актуальные
repository contracts, затем извлекай только файлы, относящиеся к task criteria.
