# Развёртывание Velvet

## Поддерживаемая матрица

| Компонент | Версия |
|---|---|
| Python | 3.13 |
| PostgreSQL | 16 |
| aiogram | 3.29.1 |
| asyncpg | 0.31.0 |
| Pillow | 11.3.0 |

Локальная установка, Docker и GitHub Actions должны использовать эту матрицу. Обновление основной версии PostgreSQL выполняется отдельной задачей с backup и restore drill.

## Режим 1: Windows и Supervisor

Этот режим подходит для текущего рабочего компьютера, автоматических обновлений и Codex.

1. Установите Python 3.13 и PostgreSQL 16.
2. Создайте virtualenv и установите `requirements.txt`.
3. Скопируйте `.env.example` в `.env`.
4. Проверьте `python main.py`.
5. Для Supervisor настройте `SUPERVISOR_TOKEN` и выполните:

```powershell
python -m velvet_supervisor
```

6. Для Codex выполните `codex`, выберите `Sign in with ChatGPT`, затем включите:

```env
CODEX_ENABLED=true
CODEX_MODEL=gpt-5.3-codex
```

Supervisor и обычный ручной запуск бота не должны одновременно управлять одним токеном Telegram.

## Режим 2: Docker Compose

### Подготовка

```powershell
Copy-Item .env.example .env
```

Обязательно замените:

```env
BOT_TOKEN=...
POSTGRES_PASSWORD=...
ALLOWED_USER_IDS=...
LOG_CHAT_ID=...
```

### Запуск PostgreSQL и бота

```powershell
docker compose up -d --build
```

Проверка:

```powershell
docker compose ps
docker compose logs -f bot
```

### Ollama

```powershell
docker compose --profile ai up -d --build
docker exec velvet-ollama ollama pull qwen3-vl:8b
```

Конфигурация бота:

```env
AI_VISION_ENABLED=true
AI_VISION_PROVIDER=ollama
AI_VISION_BASE_URL=http://ollama:11434
AI_VISION_MODEL=qwen3-vl:8b
```

Без профиля `ai` сервис Ollama не запускается.

## Хранилища

- PostgreSQL: named volume `velvet_postgres_data`;
- Ollama: named volume `velvet_ollama_data`;
- backup: каталог `./backups`;
- логи: каталог `./logs`;
- runtime: каталог `./runtime`.

Named volume PostgreSQL всё равно требует отдельной резервной копии. Docker volume не является backup, несмотря на человеческую склонность считать любой каталог с данными бессмертным.

## Healthcheck

Контейнер бота проверяет:

- подключение к `DATABASE_URL`;
- выполнение `SELECT 1`;
- доступность таблицы `schema_migrations`.

Docker уже контролирует, что основной процесс жив. Проверка Telegram polling выполняется системным центром самого бота.

## Обновление

### Windows с Supervisor

Используйте кнопки обновления и rollback Supervisor. Перед применением выполняется полный тестовый набор.

### Docker

```powershell
git pull --ff-only
docker compose build --pull bot
docker compose up -d
```

Перед обновлением схемы должна существовать проверенная копия PostgreSQL.

## Staging

Отдельная staging-среда должна иметь:

- отдельный Telegram bot token;
- отдельную PostgreSQL-базу;
- отдельный `LOG_CHAT_ID`;
- отдельные каталоги backup/logs/runtime;
- отключённую публикацию в рабочий канал;
- тестовую копию конфигурации AI.

Рабочий `BOT_TOKEN` нельзя использовать одновременно в production и staging.

## Production checklist

- `POSTGRES_PASSWORD` не совпадает с примером;
- `SUPERVISOR_TOKEN` содержит не менее 24 случайных символов;
- `ALLOWED_USER_IDS` заполнен числовым ID;
- backup создаётся и проверяется;
- restore drill проходит;
- логи не содержат токены и `DATABASE_URL`;
- AI выключен либо endpoint доступен;
- выполнен полный `python -m unittest discover -s tests -v`;
- Docker и CI используют PostgreSQL 16;
- рабочая база не используется как `TEST_DATABASE_URL`.
