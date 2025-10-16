RUBLE_PRICES: dict[int, int] = {
    50: 100,
    120: 228,
    300: 540,
    800: 1440,
    2000: 3400,
    5000: 7500,
}


def format_rubles(amount: int) -> str:
    try:
        return f"{amount:,}".replace(",", " ")
    except Exception:
        return str(amount)