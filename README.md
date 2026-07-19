# Velvet Archive Bot

Velvet — Telegram-бот для архива персонажей, публикаций и аналитики канала Velvet Anatomy. Проект работает на Python 3.13, aiogram 3 и PostgreSQL 16.

Текущая версия: `1.3.0`.

## Основные возможности

### Архив персонажей

- создание профилей и привязка к темам приватной форум-группы;
- сохранение фото, видео, анимаций и изображений-документов;
- `/save`, `/save18`, обычные упоминания и Guest Mode;
- категории пола и состава, вселенные и истории;
- несколько историй для персонажей КР;
- референсы, загрузочные сессии и фотоальбомы;
- промт конкретного материала и общий промт медиасета;
- спойлер 18+, удаление, preview тяжёлых изображений;
- публичный архив с фильтрами, лайками, подписками и уведомлениями;
- точные и визуальные дубли, ручное удаление и медиасеты.

### Публикации и аналитика

- проверка постов и Telegram-лимитов;
- черновики, редактирование, расписание, отправка и повтор после ошибки;
- импорт `result.json` и ZIP из Telegram Desktop;
- статистика канала, промтов, хэштегов и персонажей;
- аналитика обсуждений, комментариев, реакций, активности и всплесков;
- алиасы персонажей и очередь нераспознанных хэштегов;
- ручное исправление типа публикации.

### Velvet AI

При включённом `AI_VISION_ENABLED` доступны:

1. проверка качества изображения;
2. сравнение результата с референсом;
3. проверка целостности медиасета;
4. калибровка оценок по решениям владельца;
5. единый центр Velvet AI;
6. сравнение промта с результатом;
7. анализ палитры и композиции;
8. оформление публикаций Velvet Anatomy.

По умолчанию используется локальный Ollama и `qwen3-vl:8b`, но поддерживается OpenAI-совместимый endpoint. Бот продолжает работать без AI-сервиса.

### Эксплуатация

- централизованный `WorkerManager`;
- `/system`, `/health`, `/version`;
- центр ошибок с группировкой, подтверждением и уведомлениями;
- резервные копии PostgreSQL и предмиграционная защита;
- регулярный restore drill в отдельную базу;
- Velvet Supervisor для перезапуска, обновления, rollback, логов и Codex-задач;
- контрольные суммы применённых SQL-миграций;
- GitHub Actions на Python 3.13 и PostgreSQL 16.

## Быстрый запуск на Windows

```powershell
git clone https://github.com/Stellmaria/Velvet.git
cd Velvet

py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Минимальная конфигурация:

```env
BOT_TOKEN=токен_бота
DATABASE_URL=postgresql://velvet:пароль@localhost:5432/velvet
ALLOWED_USER_IDS=ваш_telegram_id
LOG_CHAT_ID=-1001234567890
ANALYTICS_CHANNEL_IDS=-1003802812639
```

Запуск:

```powershell
python main.py
```

## Docker Compose

Скопируйте пример конфигурации и задайте безопасный пароль PostgreSQL:

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

Compose запускает PostgreSQL 16 и Velvet Bot. Данные PostgreSQL хранятся в named volume, а `backups`, `logs` и `runtime` монтируются из проекта.

Для дополнительного запуска Ollama:

```powershell
docker compose --profile ai up -d --build
```

В `.env` укажите:

```env
AI_VISION_ENABLED=true
AI_VISION_BASE_URL=http://ollama:11434
AI_VISION_MODEL=qwen3-vl:8b
```

Модель внутри Ollama нужно загрузить отдельно:

```powershell
docker exec velvet-ollama ollama pull qwen3-vl:8b
```

Подробности находятся в `docs/deployment.md`.

## Доступ и роли

| Роль | Возможности |
|---|---|
| Публичный пользователь | `/start`, `/archive`, `/gallery`, навигация, лайки и подписки |
| Редактор `8179531132` | публичные функции, карточки персонажей, промты, классификация и скачивание оригинала |
| Владелец | публикации, аналитика, backup, система, Supervisor, Git, Codex и все служебные действия |

Владелец задаётся через `ALLOWED_USER_IDS` и при необходимости `ALLOWED_USERNAMES`. Числовой ID надёжнее изменяемого username.

## Основные команды

Видимое меню намеренно короткое:

```text
/start
/menu
/archive
```

Остальные действия доступны кнопками. Slash-команды сохранены как аварийный и технический резерв. Карта действий находится в разделе владельца `🧰 Все действия`.

## Резервные копии

```powershell
python scripts/backup_restore_drill.py --source-dsn $env:TEST_DATABASE_URL
```

Restore drill создаёт dump, восстанавливает его в новую временную базу, применяет миграции и сравнивает контрольные данные. Рабочая база автоматически не перезаписывается.

Подробнее: `docs/backups.md`.

## Supervisor и Codex

Supervisor запускается отдельно:

```powershell
python -m velvet_supervisor
```

Перед использованием Codex выполните `codex`, выберите `Sign in with ChatGPT`, затем настройте:

```env
CODEX_ENABLED=true
CODEX_MODEL=gpt-5.3-codex
```

Подробности: `docs/SUPERVISOR.md`.

## Тесты

```powershell
python -m unittest discover -s tests -v
```

PostgreSQL integration tests требуют отдельной тестовой базы:

```powershell
$env:TEST_DATABASE_URL="postgresql://velvet:пароль@localhost:5432/velvet_test"
python -m unittest discover -s tests -v
```

Никогда не задавайте рабочую базу в `TEST_DATABASE_URL`: тесты имеют право очищать данные.

## Архитектура

- `velvet_bot/app` — composition root, lifecycle и workers;
- `velvet_bot/application` — transport-neutral use cases владельца;
- `velvet_bot/domains` — доменные модели, repositories и services;
- `velvet_bot/infrastructure` — PostgreSQL, Telegram, filesystem и Krita adapters;
- `velvet_bot/presentation/telegram` — root Router, contracts, views и ordered router bundles;
- `velvet_bot/handlers` — временный legacy presentation layout, переносимый по доменам в P3C;
- `velvet_bot/presentation/telegram/compat.py` — единый реестр временных pre/post-import adapters.

Private PostgreSQL boundary и P2 stability закрыты. Текущий физический долг измеряется в `docs/architecture_layout_inventory.*`, актуальный статус — в `docs/development_status.md` и `docs/ARCHITECTURE_AUDIT.md`.
