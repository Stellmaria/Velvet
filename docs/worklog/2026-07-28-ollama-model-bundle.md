# 2026-07-28 — Ollama model bundle recovery

## Причина

После переноса Ollama на `E:\OllamaModels` API возвращал пустой список, хотя в каталоге оставались blobs и manifests. Старый recovery был жёстко привязан к `qwen3-vl:4b` и при восстановлении очищал comparison-модель.

## Изменение

- добавлен фиксированный набор из обычной VLM, двух uncensored VLM и uncensored text/reasoning-модели;
- добавлено восстановление имён из путей manifests;
- найденные на E модели повторно регистрируются через `ollama pull` без удаления blobs;
- отсутствующие модели скачиваются последовательно;
- `.env` обновляется атомарно и получает роли primary, compare, fallback и text;
- добавлены лимиты Ollama под 4 ГБ VRAM;
- verification различает capability `vision` и `completion`;
- добавлены тесты сохранения секретов, разбора manifests и выборочной установки.
