# 2026-08-06 — GPT Image 2 observability и local vision guard

- Дата: 2026-08-06
- ID: `gpt-image-observability-vision-guard`
- Линия/фаза: Ауф · GPT Image 2 · production observability and runtime guard
- Статус: частично
- Ветка: `feat/gpt-image-observability-vision-guard`
- Базовый commit: `76ce10d916e7901be6223534721e52adbd29dbe3`

## Перед началом

### Цель

Добавить пользователю понятную живую статистику GPT Image 2 и устранить две bootstrap-ошибки локального vision runtime.

### Исходный контекст

Production UI показывал только факт постановки задачи, экспорт и число референсов. Пользователь запросил проценты выполнения, фактические проценты Codex до/после и время выполнения. В логах также зафиксированы ошибки локального `vision-gateway`: alias `local_openai_compatible` не принимался общим клиентом, а route override `openai_compatible` на внутреннем Compose host ошибочно требовал облачную token pricing.

### Планируемый объём

- редактировать одну Telegram-карточку от очереди до завершения;
- показывать этапный процент, Codex primary/secondary до и после, очередь, выполнение и общее время;
- сохранять timing telemetry в result AI-задачи;
- нормализовать внутренний Compose provider без ослабления SSRF-проверок;
- подтвердить существующий callback-safe wallet contract `amount|currency`;
- добавить регрессии и обновить architecture inventory.

### Критерии готовности

- карточка начинается с 0% и обновляется тем же message id;
- финальная карточка показывает реальные rate-limit deltas и длительности;
- result содержит queued/start/finish и секунды ожидания/выполнения/итога;
- `local_openai_compatible` принимается runtime client как OpenAI-compatible transport;
- внутренний `vision-gateway` не требует cloud pricing;
- wallet callbacks по-прежнему не содержат `:`;
- обязательный CI зелёный.

### Риски и ограничения

- процент генерации является этапным progress очереди, поскольку Codex router не публикует точный процент рендера;
- rate-limit значения показываются только когда router вернул реальные снимки;
- облачные OpenAI-compatible endpoints по-прежнему требуют pricing и API key;
- live paid generation не выполняется в CI.

## После завершения

### Фактически сделано

- одна Telegram-карточка обновляется от 0% до завершения;
- в result сохраняются timing telemetry и реальные Codex rate-limit snapshots;
- финальная доставка показывает очередь, выполнение и полное время;
- внутренний `vision-gateway` нормализуется как локальный provider;
- общий runtime client принимает локальный provider alias;
- wallet callback-safe contract проверяется существующей регрессией.

### Миграции и совместимость

- SQL-миграций нет;
- callback prefix и структура AI-задачи обратно совместимы;
- новые payload/result поля являются добавочными;
- старые задачи без progress message id создадут отдельную progress-карточку.

### Проверки

- focused regression tests и полный CI запускаются после implementation commit.

### PR и commit

- PR и merge commit фиксируются после зелёных обязательных проверок.

### Незавершённое

- пройти required CI;
- слить в `main`;
- выполнить production deploy и живую генерацию.

### Следующий шаг

Открыть PR, дождаться зелёных обязательных проверок и выполнить merge.
