---
name: coder-pr-gate
description: Передать задачу изолированному кодеру и проверить его PR по gateway evidence до любого merge или update.
version: 1.0.0
author: Velvet
---

# Coder PR gate

1. Выбери ровно `velvet` либо `max`; не создавай cross-project задачу.
2. Удали secrets, персональные данные и нерелевантные логи из handoff.
3. Вызови `coderctl.py submit`, сохрани task/run IDs и дождись terminal state.
4. Из structured result возьми branch/PR/tests, но считай их заявлением агента.
5. Вызови `coderctl.py pr PROJECT NUMBER` и проверь head SHA, draft,
   mergeability, завершённость и успех checks.
6. Сообщи владельцу evidence и blocker. Не выполняй merge или production update
   без отдельного разрешения.
