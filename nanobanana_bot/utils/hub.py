HUB_BOT_USERNAME = "aiverse_hub_bot"
# Token-based amounts for SBP/Card methods
ALLOWED_AMOUNTS = {50, 120, 300, 800}
# Stars-based amounts for Telegram Stars (in ✨)
ALLOWED_STAR_AMOUNTS = {10, 20, 30, 50, 100, 200}


def _normalize_method(method: str) -> str:
    m = (method or "").strip().lower()
    if m in {"stars", "star", "invoice", "xtr"}:
        return "stars"
    if m in {"sbp", "fastpay", "ru_sbp"}:
        return "sbp"
    if m in {"card", "cards", "bank_card"}:
        return "card"
    return m


def make_hub_link(method: str, amount: int) -> str:
    """Generate deep link to @aiverse_hub_bot for payments.

    - method: one of 'stars', 'sbp', 'card' (supports aliases: 'invoice' -> 'stars').
    - amount: for 'sbp'/'card' — token amount from ALLOWED_AMOUNTS;
              for 'stars' — Stars amount (✨) from ALLOWED_STAR_AMOUNTS.

    Returns a URL like:
      - https://t.me/aiverse_hub_bot?start=pay-<amount>           for Stars
      - https://t.me/aiverse_hub_bot?start=pay-sbp-<amount>       for SBP
      - https://t.me/aiverse_hub_bot?start=pay-card-<amount>      for card
    """
    m = _normalize_method(method)
    if m == "stars":
        if amount not in ALLOWED_STAR_AMOUNTS:
            raise ValueError(f"Unsupported Stars amount: {amount}")
    else:
        if amount not in ALLOWED_AMOUNTS:
            raise ValueError(f"Unsupported amount: {amount}")

    if m == "stars":
        payload = f"pay-{amount}"
    elif m == "sbp":
        payload = f"pay-sbp-{amount}"
    elif m == "card":
        payload = f"pay-card-{amount}"
    else:
        raise ValueError(f"Unsupported method: {method}")

    return f"https://t.me/{HUB_BOT_USERNAME}?start={payload}"