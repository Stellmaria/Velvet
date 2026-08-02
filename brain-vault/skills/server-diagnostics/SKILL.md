---
name: server-diagnostics
description: Диагностировать состояние Velvet и Max только через фиксированные read-only представления Каэля.
version: 1.0.0
author: Velvet
---

# Server diagnostics

1. Начни с `python /opt/data/tools/monitorctl.py summary`.
2. Открой только нужное представление: `resources`, `containers`, `services`,
   `gpu`, `models`, `processes` или `incidents`.
3. Для project service используй `python /opt/data/tools/opsctl.py PROJECT status`
   и при необходимости очищенные `logs --lines 200`.
4. Разделяй наблюдение, вывод и рекомендуемое действие. Не объявляй причину без
   evidence и не выполняй исправление без разрешения.

Не используй прямые Docker/systemd/journal/proc команды и не запрашивай secrets.
