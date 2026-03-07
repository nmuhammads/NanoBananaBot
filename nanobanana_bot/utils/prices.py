RUBLE_PRICES: dict[int, int] = {
    50: 100,
    120: 228,
    300: 540,
    800: 1440,
    2000: 3600,
    5000: 9000,
}

# tokens -> USD cents
USD_PRICES_CENTS: dict[int, int] = {
    50: 130,
    120: 296,
    300: 702,
    800: 1872,
    2000: 4680,
    5000: 11700,
}

# tokens -> EUR cents
EUR_PRICES_CENTS: dict[int, int] = {
    50: 110,
    120: 251,
    300: 594,
    800: 1584,
    2000: 3960,
    5000: 9900,
}

# Base rates per token in minor units (kopecks/cents)
BASE_RATE_RUB_KOPECKS = 200
BASE_RATE_EUR_CENTS = 2.2
BASE_RATE_USD_CENTS = 2.6


def calculate_custom_price(tokens: int, currency: str) -> dict:
    currency = currency.lower()
    if currency == "eur":
        base_rate = BASE_RATE_EUR_CENTS
    elif currency == "usd":
        base_rate = BASE_RATE_USD_CENTS
    else:
        base_rate = BASE_RATE_RUB_KOPECKS

    if tokens >= 300:
        discount = 0.10
    elif tokens >= 100:
        discount = 0.05
    else:
        discount = 0.0

    amount = round(tokens * base_rate * (1 - discount))
    return {
        "amount": amount,
        "tokens": tokens,
        "discount_percent": int(discount * 100),
    }


def format_rubles(amount: int) -> str:
    try:
        return f"{amount:,}".replace(",", " ")
    except Exception:
        return str(amount)


def format_usd_cents(cents: int) -> str:
    return f"${cents / 100:.2f}"


def format_eur_cents(cents: int) -> str:
    return f"€{cents / 100:.2f}"
