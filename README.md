# Velvet Archive Bot

Telegram-бот для архива персонажей канала Velvet. Сейчас реализован первый этап: запуск через long polling и команда `/start`.

## Требования

- Python 3.13
- токен Telegram-бота от `@BotFather`

## Установка на Windows

```powershell
git clone https://github.com/Stellmaria/Velvet.git
cd Velvet

py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

Copy-Item .env.example .env
```

Откройте `.env` и замените значение `BOT_TOKEN` на токен бота:

```env
BOT_TOKEN=1234567890:telegram_token_here
```

## Запуск

```powershell
python main.py
```

После запуска откройте диалог с ботом и отправьте:

```text
/start
```

## Текущая структура

```text
Velvet/
├── main.py
├── requirements.txt
├── .env.example
└── velvet_bot/
    ├── config.py
    └── handlers/
        └── start.py
```

Токен хранится только в локальном файле `.env`, который исключён из Git.
