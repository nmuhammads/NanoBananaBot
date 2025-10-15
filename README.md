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
4. Запустите бота локально:
   ```bash
   python -m nanobanana_bot.main
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
    ├── main.py
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
- В среде, поддерживающей Procfile: используйте `worker: python -m nanobanana_bot.main`.
- Убедитесь, что переменные окружения передаются в runtime.

## Лицензия
- Внутренний проект. Лицензирование по вашей политике.