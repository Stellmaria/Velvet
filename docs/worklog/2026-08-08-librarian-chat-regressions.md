# Исправление Librarian/Arthur regressions из production-разбора

- Дата: 2026-08-08
- ID: `2026-08-08-librarian-chat-regressions`
- Линия/фаза: hotfix / librarian runtime safety
- Статус: `завершено`
- Ветка: `fix/librarian-chat-regressions`
- Базовый commit: `66f0993780a1428b260336929f2050b424aebf1e`

## Перед началом

### Цель

Закрыть дефекты, подтверждённые в production-разборе Arthur archive: не откатывать runtime image и analyzer при librarian reconcile, не публиковать Arthur reports в неявно унаследованный недоступный chat и сделать `/archive status` менее вводящим в заблуждение при одновременном discovery и processing.

### Исходный контекст

`deploy/hermes-librarian/install.sh` принудительно записывал базовый analyzer version и напрямую пересоздавал `bot` через Compose. При stale `VELVET_IMAGE` в `.env.server` это вернуло старый runtime image, хотя Git checkout оставался новым. Отдельно Arthur report publisher получал fallback на Storage chat/topic, который отдельному Arthur bot оказался недоступен (`Bad Request: chat not found`). В `/archive status` live backlog мог оставаться неизменным, пока `completed` рос, из-за чего работающий archive loop выглядел остановленным.

### Планируемый объём

- сохранять непустой operator-selected `STORAGE_LIBRARIAN_ANALYZER_VERSION`;
- использовать существующий `recreate_bot_preserving_image.sh` для librarian lifecycle recreate;
- не наследовать Storage report chat/topic без явного `ARTHUR_REPORT_CHAT_ID`;
- пояснить live backlog в `/archive status`;
- закрепить контракты regression tests;
- не ослаблять hard chunk limit и 180-second retry timeout.

### Критерии готовности

- reconcile не меняет выбранную analyzer version;
- reconcile не выбирает runtime image из stale `.env.server`;
- отсутствие explicit Arthur report target не вызывает попыток публикации в чужой Storage chat;
- `/archive status` отличает processed jobs от текущего backlog;
- обязательный CI зелёный.

### Риски и ограничения

Патч не меняет правила chunking, retry budget или inference timeout. `ARTHUR_REPORT_CHAT_ID` становится единственным явным источником report destination; если он не задан, background reports отключены, а результаты остаются доступны через Arthur commands и БД.

## После завершения

### Фактически сделано

Installer сохраняет существующую analyzer version, выводит фактически выбранное значение и пересоздаёт bot через image-preserving helper. Arthur report destination больше не fallback-ится на `TELEGRAM_STORAGE_CHAT_ID`, hardcoded chat или Storage topic. Archive status показывает `Processed jobs`, `Queued now`, `Running now` и поясняет, что backlog может не уменьшаться во время discovery.

### Изменённые модули и контракты

- `deploy/hermes-librarian/install.sh`: analyzer/image preservation;
- `velvet_bot/core/config/arthur.py`: explicit-only report target;
- `velvet_bot/presentation/telegram/arthur_librarian.py`: live backlog semantics;
- `tests/test_librarian_chat_regressions.py`: regression coverage;
- `docs/worklog/2026-08-08-librarian-chat-regressions.md`: запись hotfix.

### Миграции и совместимость

Миграции БД не требуются. Для background Telegram reports теперь требуется явный `ARTHUR_REPORT_CHAT_ID`; `ARTHUR_REPORT_THREAD_ID` учитывается только при заданном report chat.

### Проверки

PR запускает обязательные GitHub Actions: tests, type check, Docker build, security supply chain, project notes contract и branch protection contract.

### PR и commit

PR: #747 `Fix librarian reconcile and Arthur archive regressions`.

### Незавершённое

Production deployment не входит в эту GitHub-операцию. Текущий archive run не останавливается и его safety limits не меняются.

### Следующий шаг

Слить PR после зелёного CI; production применить отдельным штатным обновлением.
