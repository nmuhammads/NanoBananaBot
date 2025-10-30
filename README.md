# Seedream Bot

Seedream Bot — Telegram-бот для генерации изображений через официальное KIE API (Seedream V4), созданный на основе архитектуры текущего проекта.

- Стек: `Python 3.11`, `aiogram 3.22.0`, `aiohttp`, `redis`, `supabase`.
- Общие сервисы: единая база пользователей в Supabase и общий кеш Redis для баланса токенов.
- API: KIE official base `https://api.kie.ai/api/v1` (jobs/createTask, jobs/recordInfo).
 - Models (configurable via env): `SEEDREAM_MODEL_T2I`, `SEEDREAM_MODEL_EDIT`.
   Defaults: `bytedance/seedream-v4-text-to-image`, `bytedance/seedream-v4-edit`.

## Быстрый старт

1. Склонируйте или скопируйте папку `SeedreamBot` в отдельный репозиторий (имя папки произвольное).
2. Создайте файл `.env` по примеру `.env.example` и заполните значения:
   - `BOT_TOKEN`
   - `SUPABASE_URL`, `SUPABASE_KEY`
   - `REDIS_URL`
   - `SEEDREAM_API_BASE`, `SEEDREAM_API_KEY`
   - `TRIBUTE_API_KEY`, `TRIBUTE_PRODUCT_MAP` (для оплаты через Tribute)
3. Создайте и активируйте виртуальное окружение, установите зависимости:
   ```bash
   python -m venv .venv
   .venv\\Scripts\\activate
   pip install -r requirements.txt
   ```
4. Запустите сервер локально (uvicorn):
   ```bash
   uvicorn seedream_bot.webapp:app --host 0.0.0.0 --port 8000
   ```

## Команды
- `/start` — приветствие, регистрация пользователя (если нет), показ баланса токенов.
- `/help` — подсказка по использованию.
- `/generate <prompt>` — генерация изображения по текстовому запросу.

## Архитектура
```
SeedreamBot/
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
        └── seedream.py
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
     web: uvicorn seedream_bot.webapp:app --host 0.0.0.0 --port $PORT
     ```
  3. Убедитесь, что переменные окружения (`BOT_TOKEN`, Supabase, Redis, Seedream/KIE) заданы.
  4. После старта Railway веб-сервиса бот автоматически установит webhook на `WEBHOOK_URL + WEBHOOK_PATH`.

### Локальная проверка uvicorn
```bash
uvicorn seedream_bot.webapp:app --host 0.0.0.0 --port 8000
```
Затем задайте временный публичный адрес (например, через ngrok) в `WEBHOOK_URL` и проверьте получение обновлений.

## Лицензия
- Внутренний проект. Лицензирование по вашей политике.

## Оплата через хаб @aiverse_hub_bot
- Бот формирует инлайн URL‑кнопки, ведущие в хаб с `start`‑пейлоадами.
- Методы: `stars` (Telegram Stars), `sbp` (СБП), `card` (карта).
- Суммы: `50`, `120`, `300`, `800` — именно эти значения (совпадают с `TRIBUTE_PRODUCT_MAP`).
- Примеры диплинков:
  - Stars: `https://t.me/aiverse_hub_bot?start=pay-50`, `...pay-120`, `...pay-300`, `...pay-800`
  - СБП: `https://t.me/aiverse_hub_bot?start=pay-sbp-50`, `...pay-sbp-120`, `...pay-sbp-300`, `...pay-sbp-800`
  - Карта: `https://t.me/aiverse_hub_bot?start=pay-card-50`, `...pay-card-120`, `...pay-card-300`, `...pay-card-800`
- Поведение:
  - Stars — мгновенно открывается счёт (0 кликов в хабе).
  - Tribute (СБП/карта) — сразу приходит одна кнопка продукта на выбранную сумму (1 клик).