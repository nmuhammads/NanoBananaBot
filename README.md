# NanoBanana Bot

NanoBanana Bot — новый Telegram-бот для генерации изображений нейросетью NanoBanana, созданный на основе архитектуры текущего проекта, но как отдельный независимый репозиторий/папка.

- Стек: `Python 3.11`, `aiogram 3.22.0`, `aiohttp`, `redis`, `supabase`.
- Общие сервисы: единая база пользователей в Supabase и общий кеш Redis для баланса токенов.
- API: NanoBanana `https://kie.ai/nano-banana`.

## Быстрый старт

1. Склонируйте или скопируйте папку `NanoBananaBot` в отдельный репозиторий.
2. Создайте файл `.env` по примеру `.env.example` и заполните значения:
   - `BOT_TOKEN`
   - `SUPABASE_URL`, `SUPABASE_KEY`
   - `REDIS_URL`
   - `NANOBANANA_API_BASE`, `NANOBANANA_API_KEY`
3. Создайте и активируйте виртуальное окружение, установите зависимости:
   ```bash
   python -m venv .venv
   .venv\\Scripts\\activate
   pip install -r requirements.txt
   ```
4. Запустите сервер локально (uvicorn):
   ```bash
   uvicorn nanobanana_bot.webapp:app --host 0.0.0.0 --port 8000
   ```

## Команды
- `/start` — приветствие, регистрация пользователя (если нет), показ баланса токенов.
- `/help` — подсказка по использованию.
- `/generate <prompt>` — генерация изображения по текстовому запросу.

## Архитектура
```
NanoBananaBot/
├── Procfile
├── README.md
├── requirements.txt
├── runtime.txt
├── .env.example
└── nanobanana_bot/
    ├── __init__.py
    ├── webapp.py
    ├── config.py
    ├── cache.py
    ├── database.py
    ├── handlers/
    │   ├── __init__.py
    │   ├── start.py
    │   └── generate.py
    ├── middlewares/
    │   ├── __init__.py
    │   ├── logging.py
    │   └── rate_limit.py
    └── utils/
        ├── __init__.py
        └── nanobanana.py
```

## Примечания по версиям
- aiogram `3.22.0` используется согласно актуальной документации: позволяет работать через `Dispatcher`, `Router` и `DefaultBotProperties(parse_mode=HTML)`.
- Для Supabase используется клиент `supabase` (python), ключ `service-role` обязателен для записи.
- Redis — асинхронный клиент `redis.asyncio`.

## Деплой
Для деплоя на Railway через uvicorn (webhook):
  1. Добавьте переменные окружения:
     - `WEBHOOK_URL` — публичный URL вашего Railway сервиса, например `https://<app>.up.railway.app`.
     - `WEBHOOK_PATH` — путь для приёма обновлений Telegram, по умолчанию `/webhook`.
     - `WEBHOOK_SECRET_TOKEN` — необязательный секрет для валидации запросов Telegram.
  2. Procfile должен содержать:
     ```
     web: uvicorn nanobanana_bot.webapp:app --host 0.0.0.0 --port $PORT
     ```
  3. Убедитесь, что переменные окружения (`BOT_TOKEN`, Supabase, Redis, NanoBanana) заданы.
  4. После старта Railway веб-сервиса бот автоматически установит webhook на `WEBHOOK_URL + WEBHOOK_PATH`.

### Локальная проверка uvicorn
```bash
uvicorn nanobanana_bot.webapp:app --host 0.0.0.0 --port 8000
```
Затем задайте временный публичный адрес (например, через ngrok) в `WEBHOOK_URL` и проверьте получение обновлений.

## Лицензия
- Внутренний проект. Лицензирование по вашей политике.