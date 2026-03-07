HUB_BOT_USERNAME = "aiverse_hub_bot"

# Fixed package amounts for SBP method (in tokens)
ALLOWED_SBP_AMOUNTS = {50, 120, 300, 800}
# Backward-compatible alias
ALLOWED_AMOUNTS = ALLOWED_SBP_AMOUNTS
# Stars-based amounts for Telegram Stars (in ✨)
ALLOWED_STAR_AMOUNTS = {10, 20, 30, 50, 100, 200}
# Custom card amount limits (in tokens)
MIN_CUSTOM_TOKENS = 50
MAX_CUSTOM_TOKENS = 10000


def _normalize_method(method: str) -> str:
    m = (method or "").strip().lower()
    if m in {"stars", "star", "invoice", "xtr"}:
        return "stars"
    if m in {"sbp", "fastpay", "ru_sbp"}:
        return "sbp"
    if m in {"card", "cards", "bank_card"}:
        return "card_rub"
    if m in {"card_rub", "rub_card"}:
        return "card_rub"
    if m in {"card_usd", "usd_card"}:
        return "card_usd"
    if m in {"card_eur", "eur_card"}:
        return "card_eur"
    return m


def is_valid_custom_tokens(amount: int) -> bool:
    return MIN_CUSTOM_TOKENS <= int(amount) <= MAX_CUSTOM_TOKENS


def make_hub_link(method: str, amount: int) -> str:
    """Generate deep link to @aiverse_hub_bot for payments."""
    m = _normalize_method(method)
    amount = int(amount)

    if m == "stars":
        if amount not in ALLOWED_STAR_AMOUNTS:
            raise ValueError(f"Unsupported Stars amount: {amount}")
    elif m == "sbp":
        if amount not in ALLOWED_SBP_AMOUNTS:
            raise ValueError(f"Unsupported SBP amount: {amount}")
    elif m in {"card_rub", "card_usd", "card_eur"}:
        if not is_valid_custom_tokens(amount):
            raise ValueError(f"Unsupported custom card amount: {amount}")
    else:
        raise ValueError(f"Unsupported method: {method}")

    if m == "stars":
        payload = f"pay-{amount}"
    elif m == "sbp":
        payload = f"pay-sbp-{amount}"
    elif m in {"card_rub", "card_usd", "card_eur"}:
        payload = f"pay-{m}-{amount}"
    else:
        raise ValueError(f"Unsupported method: {method}")

    return f"https://t.me/{HUB_BOT_USERNAME}?start={payload}"
