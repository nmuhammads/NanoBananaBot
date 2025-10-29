### **Обзор архитектуры платежей**

Система оплаты в этом боте гибридная и использует два основных подхода:

1.  **Внешняя оплата через "Хаб"-бота**: Для оплаты картой, СБП и даже Telegram Stars используется перенаправление пользователя в центральный платежный бот (`@aiverse_hub_bot`) с помощью специальных диплинков. Это основной и самый современный способ. Он позволяет централизованно управлять платежами и не дублировать логику в каждом боте.
2.  **Внутренняя (нативная) оплата Telegram Stars**: В коде также присутствует логика для создания и обработки счетов на оплату (инвойсов) прямо внутри текущего бота. Это более старый метод, но он полностью рабочий и является стандартом Telegram для цифровых товаров.

---

### **Инструкция для реализации в новом боте**

#### **Часть 1: Реализация оплаты через "Хаб"-бота (СБП, Карта, Stars)**

Этот метод является предпочтительным. Он прост в реализации, так как основную работу выполняет внешний бот-хаб.

**Шаг 1: Создайте обработчик команды пополнения**

-   Создайте команду (например, `/topup` или кнопка "Пополнить баланс").
-   В ответ на команду отправьте пользователю сообщение с предложением выбрать метод оплаты и прикрепите клавиатуру с кнопками.

```python
# Пример клавиатуры выбора метода
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def method_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="СБП", callback_data="topup_method:sbp")],
            [InlineKeyboardButton(text="Банковская карта", callback_data="topup_method:card")],
            [InlineKeyboardButton(text="Telegram Stars", callback_data="topup_method:stars")],
        ]
    )
```

**Шаг 2: Реализуйте генерацию диплинков**

-   Создайте функцию, которая будет генерировать диплинки на платежный хаб (`@aiverse_hub_bot`).
-   Формат диплинка зависит от метода оплаты и суммы.

```python
# Константы
HUB_BOT_USERNAME = "aiverse_hub_bot"
# Суммы пополнения в токенах, которые поддерживает хаб
ALLOWED_AMOUNTS = {50, 120, 300, 800}

def make_hub_link(method: str, amount: int) -> str:
    """
    Генерирует диплинк на @aiverse_hub_bot для оплаты.
    - method: 'sbp', 'card' или 'stars'.
    - amount: количество токенов, должно быть в ALLOWED_AMOUNTS.
    """
    method = method.strip().lower()
    if amount not in ALLOWED_AMOUNTS:
        raise ValueError(f"Неподдерживаемая сумма: {amount}")

    payload = ""
    if method == "stars":
        payload = f"pay-{amount}"
    elif method in ["sbp", "card"]:
        payload = f"pay-{method}-{amount}"
    else:
        raise ValueError(f"Неподдерживаемый метод: {method}")

    return f"https://t.me/{HUB_BOT_USERNAME}?start={payload}"
```

**Шаг 3: Настройте отображение цен (опционально)**

-   Чтобы показывать пользователям примерную стоимость пакетов в рублях прямо на кнопках, вы можете создать файл `utils/prices.py`.
-   Этот файл будет содержать словарь, сопоставляющий количество токенов с их ценой в рублях.

-   **Пример `utils/prices.py`**:
    ```python
    # Словарь: количество токенов -> цена в рублях
    RUBLE_PRICES: dict[int, int] = {
        50: 100,
        120: 228,
        300: 540,
        800: 1440,
    }

    def format_rubles(amount: int) -> str:
        """Форматирует число в строку вида '1 440'."""
        try:
            return f"{amount:,}".replace(",", " ")
        except Exception:
            return str(amount)
    ```

**Шаг 4: Покажите пользователю клавиатуру с суммами**

-   После того как пользователь выберет метод оплаты (на шаге 1), отправьте ему новую клавиатуру.
-   Каждая кнопка на этой клавиатуре будет содержать диплинк, ведущий на оплату в хаб-боте.

```python
# Пример обработчика колбэка выбора метода
# Импортируем данные о ценах
from ..utils.prices import RUBLE_PRICES, format_rubles

@router.callback_query(F.data.startswith("topup_method:"))
async def choose_method_handler(callback: CallbackQuery):
    method = callback.data.split(":")[1]

    # Создаем клавиатуру с диплинками
    buttons = []
    for amount in sorted(ALLOWED_AMOUNTS):
        url = make_hub_link(method, amount)

        # Формируем текст для кнопки
        # Если метод - СБП или карта, и цена есть в словаре, добавляем ее
        if method in ["sbp", "card"]:
            rub_price = RUBLE_PRICES.get(amount)
            label = (
                f"{amount} Токенов"
                if rub_price is None
                else f"{amount} Токенов ~ {format_rubles(rub_price)} руб"
            )
        else: # для Stars просто показываем количество
            label = f"{amount} ✨"

        buttons.append([InlineKeyboardButton(text=label, url=url)])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.answer(
        "Выберите пакет для пополнения:",
        reply_markup=keyboard,
    )
    await callback.answer()
```

**Шаг 5 (Важно): Настройте карту продуктов Tribute**

-   Для того чтобы платежная система Tribute знала, какой именно продукт покупает пользователь, необходимо создать "карту" (mapping) между количеством токенов и ID продукта в системе Tribute.
-   Эта настройка выполняется с помощью переменной окружения `TRIBUTE_PRODUCT_MAP`.

-   **Формат**: Переменная должна содержать строку в формате JSON.
    -   **Ключ** — это количество токенов (например, `"50"`).
    -   **Значение** — это ID продукта из Tribute (например, `"83550"`).

-   **Пример**:
    ```bash
    export TRIBUTE_PRODUCT_MAP='{"50":"83550", "120":"83551", "300":"83552", "800":"83553"}'
    ```

-   Ваш бот при запуске должен читать эту переменную, парсить JSON и использовать эту карту для связи сумм с конкретными продуктами при обращении к API Tribute. В исследуемом проекте это реализовано в `config.py`.

**Готово!** На этом реализация внешней оплаты завершена. Бот-хаб сам обработает платеж и уведомит пользователя. Ваш бот не нуждается в обработке успешных платежей, так как баланс, скорее всего, синхронизируется на уровне общей базы данных.

---

#### **Часть 2: Реализация нативной оплаты Telegram Stars (внутри бота)**

Этот метод используется, если вы хотите обрабатывать платежи за Stars самостоятельно, без внешнего хаба.

**Шаг 1: Создайте обработчик для отправки инвойса**

-   Пользователь выбирает количество Stars для покупки.
-   Бот вызывает метод `send_invoice` из Bot API.

```python
from aiogram.types import LabeledPrice

async def send_stars_invoice(message: Message, amount: int):
    """Отправляет счет на оплату в Telegram Stars."""
    if amount <= 0:
        raise ValueError("Сумма должна быть положительной")

    await message.bot.send_invoice(
        chat_id=message.chat.id,
        title="Пополнение баланса",
        description=f"Покупка {amount} токенов",
        payload=f"topup_stars:{amount}",  # Уникальный идентификатор платежа
        provider_token="",  # Для Stars токен не нужен
        currency="XTR",  # Валюта Telegram Stars
        prices=[LabeledPrice(label=f"{amount} токенов", amount=amount)],
        start_parameter=f"topup_{amount}", # Параметр для диплинка, если нужен
    )
```

**Шаг 2: Обработайте Pre-Checkout Query**

-   Telegram отправляет этот запрос вашему боту перед списанием средств. Вы должны подтвердить, что готовы принять платеж.

```python
from aiogram.types import PreCheckoutQuery

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    # Просто подтверждаем готовность принять платеж
    await pre_checkout_query.answer(ok=True)
```

**Шаг 3: Обработайте успешный платеж**

-   После успешной оплаты Telegram присылает вашему боту сервисное сообщение `SuccessfulPayment`.

```python
from aiogram.filters import F
from aiogram.types import Message

@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payment_info = message.successful_payment
    if payment_info.currency != "XTR":
        await message.answer("Произошла ошибка: валюта платежа не Stars.")
        return

    amount = payment_info.total_amount
    user_id = message.from_user.id

    # 1. Обновите баланс пользователя в вашей базе данных
    # await db.add_tokens(user_id=user_id, amount=amount)
    # current_balance = await db.get_balance(user_id=user_id)

    # 2. Сообщите пользователю об успешном пополнении
    await message.answer(
        f"Оплата прошла успешно! Ваш баланс пополнен на {amount} ✨.\n"
        f"Текущий баланс: {current_balance} токенов."
    )
```

Эта инструкция охватывает оба механизма, реализованные в исследуемом проекте. Для нового бота рекомендуется использовать **Часть 1**, так как она соответствует текущей логике и упрощает поддержку.