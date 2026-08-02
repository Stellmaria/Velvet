---
name: memory-curation
description: Проверить memory proposal, удалить дубли и безопасно направить versioned изменение через профильного кодера.
version: 1.0.0
author: Velvet
---

# Memory curation

1. Проверь соответствие `memory-proposal.schema.json`.
2. Отклони секреты, raw logs, полный диалог, догадки и лишние персональные данные.
3. Найди evidence и выбери одну scope; конфликтующий факт пометь stale.
4. Отклони временную деталь без будущей ценности либо задай `expires_at`.
5. Проверь дубли в SOUL, AGENTS, project notes и Vault.
6. Для принятого proposal создай handoff соответствующему кодеру на Git PR.

Не редактируй runtime MEMORY или Vault произвольной shell-командой.
