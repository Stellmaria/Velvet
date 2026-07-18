# Сессия: Фаза 18Y — Ollama vision repository и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18y-ollama-vision-acquire`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18Y
- Статус: частично
- Ветка: `agent/phase18y-ollama-vision-acquire`
- Базовый commit: `4b7a5933c8cd4202e86f6989af7d73cbdd9cbaef`

## Перед началом

### Цель

Перевести два connection point repository-контура `velvet_bot/ollama_vision.py` с приватного `Database._require_pool()` на публичный `Database.acquire()` без изменения Ollama request/response lifecycle.

### Исходный контекст

- baseline до работы: 88 внешних обращений в 23 production-файлах;
- целевой модуль: `velvet_bot/ollama_vision.py`, 2 connection points.

### Планируемый объём

1. Перевести оба repository connection point на `Database.acquire()`.
2. Сохранить SQL, state transitions, JSON persistence и retries.
3. Добавить regression-тесты.
4. Уменьшить baseline до 86/22 и обновить документы.

### Критерии готовности

- целевой repository не содержит `._require_pool()`;
- оба метода используют публичную границу;
- baseline равен 86/22;
- полный PR CI зелёный.

### Риски и ограничения

- Ollama HTTP-клиент и модель не изменяются;
- миграции не изменяются;
- Heavy Runtime ТЗ не включается.

## После завершения

### Фактически сделано

Ожидается реализация.

### Миграции и совместимость

Ожидается реализация.

### Проверки

Ожидается реализация и CI.

### PR и commit

Ожидается открытие PR.

### Незавершённое

Реализация и проверки.

### Следующий шаг

Фаза 18Z: resilient AI vision repository.
