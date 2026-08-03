---
name: codex-first
description: Передать инженерную задачу прямого Telegram coder-бота в изолированный Codex runner до использования provider-инструментов.
version: 1.0.0
author: Velvet
---

# Codex-first delegation

Используй этот skill только в Hermes chat gateway, когда задана переменная
`HERMES_CODEX_DELEGATE_URL`. Внутри уже оркестрированного Codex run не вызывай
делегатор повторно.

1. Для анализа или изменения repository сначала передай полную задачу через stdin:

   ```bash
   python /app/codex_delegate.py <<'TASK'
   <точный текст задачи и критерии готовности>
   TASK
   ```

2. Дождись terminal JSON. Поля `requested_route`, `actual_route`,
   `fallback_reason` и `mutation_started` являются частью обязательного evidence.
3. Если `status=completed`, не повторяй работу собственными provider-tools.
4. Если runner сам выполнил provider fallback, используй его единственный
   результат и не запускай второй provider run.
5. Если `mutation_started=true`, запрещено автоматически повторять задачу другим
   движком. Сообщи blocker владельцу.
6. Собственные provider-tools разрешены только когда делегатор завершился до
   создания run и не начал mutation.
7. Никогда не печатай `CODEX_RUNNER_API_KEY`, Byesu key или полный environment.
