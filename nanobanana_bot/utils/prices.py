RUBLE_PRICES: dict[int, int] = {
    50: 100,
    120: 228,
    300: 540,
    800: 1440,
    2000: 3400,
    5000: 7500,
}

USD_PRICES: dict[int, int] = {
    50: 1.3,
    120: 2.8,
    300: 6.8,
    800: 18,
    2000: 42,
    5000: 95,
}


def format_rubles(amount: int) -> str:
    try:
        return f"{amount:,}".replace(",", " ")
    except Exception:
        return str(amount)


def format_usd(amount: int) -> str:
    try:
        return f"{amount:,}".replace(",", " ")
    except Exception:
        return str(amount)