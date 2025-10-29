RUBLE_PRICES: dict[int, int] = {
    50: 100,
    120: 228,
    300: 540,
    800: 1440,
    2000: 3400,
    5000: 7500,
}

USD_PRICES: dict[int, int] = {
    50: 2,
    120: 4,
    300: 9,
    800: 24,
    2000: 55,
    5000: 120,
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