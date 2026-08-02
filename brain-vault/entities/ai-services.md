---
id: entity-ai-services
type: entity
scope: shared
status: active
owner: kael
sensitivity: internal
version: 1
updated: 2026-08-02
---

# Неагентные AI-сервисы

Не каждая модель является сущностью с душой и памятью. Velvet AI/Qwen vision,
cloud roleplay, media generation providers и Krita workers являются
request-scoped capabilities приложения.

| Контур | Получает | Не получает | Источник состояния |
|---|---|---|---|
| Velvet AI / local vision | Один bounded media-analysis request | SOUL, task ledger, cross-workspace memory | PostgreSQL jobs/profiles + config |
| Cloud roleplay | Один character/dialogue request | Server control, provider secrets в prompt | Application session + metering |
| Kie/GRS media providers | Typed generation payload | Диалоги, Vault, operator context | Durable job/provider records |
| Krita workers | Typed render request и разрешённые assets | Agent memory, GitHub, production control | Queue/result manifests |

Каэль наблюдает их health и маршрутизирует исправление профильному кодеру, но
не превращает provider в автономного агента и не выдаёт ему общую memory. Общие
политики хранятся в коде/Vault, короткое состояние — в соответствующей очереди
или сессии, результат — в domain storage.
