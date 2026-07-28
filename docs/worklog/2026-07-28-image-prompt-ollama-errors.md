# Сессия: устойчивость image-to-prompt при сбоях Ollama

- Дата: 2026-07-28
- ID: `2026-07-28-image-prompt-ollama-errors`
- Линия/фаза: Velvet AI / стабилизация image-to-prompt
- Статус: `частично`
- Ветка: `agent/fix-image-prompt-ollama-errors`
- Базовый commit: `ff70ad97133ee6508391082509a195af17ef8898`

## Перед началом

### Цель

Устранить аварийный сценарий операции `Изображение → промт`, при котором
несовместимая модель возвращала бесполезный HTTP 400, следующая модель закрывала
соединение, а остановившийся Ollama порождал повторные ERROR-traceback и
`WinError 10061`.

### Исходный контекст

После merge PR #331 в живой Windows-проверке основная модель
`hf.co/mradermacher/Qwen3-VL-4B-Instruct-abliterated-GGUF:Q4_K_M` вернула
`HTTP Error 400: Bad Request`. Сравнительная `qwen3-vl:8b` закрыла соединение,
после чего локальный endpoint `127.0.0.1:11434` перестал принимать запросы.
Существующий клиент не извлекал JSON-поле `error` из HTTP-ответа, не проверял
vision capability модели и поднимал общий `RuntimeError`, если обе модели
завершались ожидаемым отказом.

### Планируемый объём

- сохранить диагностическое поле `error` из HTTP-ответов Ollama;
- различать ошибки запроса модели и недоступность локального провайдера;
- проверять capability `vision` через `/api/show` до передачи изображения;
- не создавать traceback уровня ERROR для ожидаемого отказа модели или Ollama;
- убрать сырой Hugging Face GGUF из рекомендуемой конфигурации;
- добавить безопасную стартовую конфигурацию и Windows-диагностику;
- покрыть изменения regression-тестами.

### Критерии готовности

- HTTP 400 показывает фактическую причину Ollama;
- HTTP 5xx и сетевой отказ классифицируются как недоступность провайдера;
- модель с объявленными capabilities без `vision` отклоняется до `/api/chat`;
- все ожидаемые отказы корректно завершают AI-задание без ERROR-traceback;
- частичный результат одной модели сохраняет прежнее поведение;
- project notes contract, tests, type check и Docker build проходят в PR;
- одиночная `qwen3-vl:4b` проверяется на целевой Windows-машине после merge.

### Риски и ограничения

GitHub Actions не может проверить локальную видеопамять, Windows-процесс Ollama
и конкретную установленную модель. Отсутствующее поле `capabilities` оставлено
совместимым со старыми endpoint: запрос не блокируется, а фактический отказ
по-прежнему обрабатывается через HTTP-диагностику. Живая проверка обязательна.

## После завершения

### Фактически сделано

- `VisionClient._read_json` отдельно обрабатывает `HTTPError` и извлекает JSON-поле
  `error` из ответа Ollama;
- HTTP 4xx преобразуется в `VisionAnalysisError`, HTTP 5xx и сетевые отказы в
  `VisionProviderUnavailable`;
- `ImageToPromptClient` проверяет `/api/show` и capability `vision` до подготовки
  и отправки изображения;
- модель без vision получает понятное сообщение с рекомендацией использовать
  официальную `qwen3-vl:4b`;
- ожидаемые ошибки моделей сохраняются в AI-задании и отправляются пользователю
  без повторного traceback уровня ERROR;
- частичный успех одной из сравнительных моделей остаётся рабочим;
- `.env.example` переведён с `qwen3-vl:8b` на стартовую `qwen3-vl:4b`;
- документация использует официальные Ollama-модели `qwen3-vl:4b` и
  `qwen3-vl:2b`, предупреждает о сыром multimodal GGUF и описывает проверку
  Windows `server.log`;
- добавлены regression-тесты HTTP 400, HTTP 500, отсутствующей vision capability
  и обратной совместимости endpoint без списка capabilities.

### Миграции и совместимость

Миграции базы данных не требуются. Настройки `AI_VISION_*`, callback data,
AI-job kind и формат результатов не меняются. Пустой `AI_VISION_COMPARE_MODEL`
по-прежнему включает одиночный режим. Endpoint без поля `capabilities` не
отклоняется автоматически.

### Проверки

- новый test module покрывает HTTP 400 с JSON error body;
- новый test module покрывает HTTP 500 как provider unavailable;
- проверяется ранний отказ модели без capability `vision`;
- проверяется совместимость Ollama-ответа без поля `capabilities`;
- project notes contract первоначально выявил неполную рабочую запись; запись
  приведена к обязательному формату;
- полный tests workflow, type check и Docker build выполняются GitHub Actions;
- живая Windows/Ollama-проверка ещё не выполнена.

### PR и commit

Draft PR #333: `Fix Ollama image-to-prompt failures`.

### Незавершённое

Нужно дождаться зелёного CI, затем на Windows перезапустить Ollama, установить
`qwen3-vl:4b`, оставить `AI_VISION_COMPARE_MODEL` пустым и повторить один
image-to-prompt запрос. Сравнение моделей включать только после стабильного
одиночного запуска.

### Следующий шаг

После CI слить PR #333 отдельным hotfix перед продолжением #332. На production
использовать `AI_VISION_MODEL=qwen3-vl:4b`, пустой compare model и timeout 600
секунд; при повторном завершении Ollama проверить `%LOCALAPPDATA%\Ollama\server.log`.
