---
name: codex-first
description: Передать инженерную задачу прямого Telegram coder-бота в изолированный Codex runner с явным tier-contract.
version: 2.0.0
author: Velvet
---

# Codex-first tier-aware delegation

Используй этот skill только в Hermes chat gateway, когда задана переменная
`HERMES_CODEX_DELEGATE_URL`. Внутри уже оркестрированного Codex run не вызывай
делегатор повторно.

1. До делегирования отдельно определи:
   - `task_type`: `general`, `code`, `read_only`, `documentation` или `incident`;
   - `complexity`: `small`, `standard` или `complex`;
   - `risk`: `low`, `medium`, `high` или `critical`;
   - `mutation_policy`: `read_only`, `workspace_write` или `isolated_pr_only`;
   - `requested_tier`: `small`, `standard`, `complex` или `high_risk`.
2. Не выводи риск только из длины prompt или одного ключевого слова. Учитывай
   поверхность изменений, данные, обратимость, production-влияние и число сервисов.
3. Для анализа или изменения repository передай полную задачу через stdin и
   явные аргументы:

   ```bash
   python /app/codex_delegate.py \
     --task-type <task_type> \
     --complexity <complexity> \
     --risk <risk> \
     --mutation-policy <mutation_policy> \
     --tier <requested_tier> <<'TASK'
   <точный текст задачи и критерии готовности>
   TASK
   ```

   `--model` не указывай без явной причины. Если он указан, модель не может быть
   ниже модели выбранного tier.
4. Для `complex` и `high_risk` всегда используй
   `--mutation-policy isolated_pr_only`; основной Codex route должен выбрать Sol.
5. Дождись terminal JSON. Поля `requested_tier`, `selected_primary_model`,
   `selected_provider_route`, `actual_route`, `attempted_models`,
   `attempted_routes`, `fallback_reason` и `mutation_started` являются частью
   обязательного evidence.
6. Если `status=completed`, не повторяй работу собственными provider-tools.
7. Если runner сам выполнил provider fallback, используй его единственный
   результат и не запускай второй provider run.
8. Если `mutation_started=true` или зафиксирован execution event, запрещено
   автоматически повторять задачу другим движком. Сообщи blocker владельцу.
9. Собственные provider-tools разрешены только когда делегатор завершился до
   создания run и не начал mutation.
10. Никогда не печатай `CODEX_RUNNER_API_KEY`, Byesu key, credential-group env
    names или полный environment.
