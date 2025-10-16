from typing import Dict, Any

SUPPORTED_LANGS = {"ru", "en"}


def normalize_lang(lang: str | None) -> str:
    if not lang:
        return "ru"
    lang = lang.lower()
    if lang.startswith("ru"):
        return "ru"
    if lang.startswith("en"):
        return "en"
    return "ru"


STRINGS: Dict[str, Dict[str, str]] = {
    "ru": {
        # Keyboard labels
        "kb.profile": "Профиль 👤",
        "kb.topup": "Пополнить баланс ✨",
        "kb.generate": "Сгенерировать 🖼️",

        # Start
        "start.welcome": (
            "🍌 <b>NanoBanana Bot</b>\n\n"
            "Привет, {name}! Добро пожаловать 👋\n\n"
            "✨ Возможности:\n"
            "• Генерация изображений по тексту\n"
            "• Текст + фото, несколько фото\n\n"
            "💳 Стоимость: <b>4 токена</b> за изображение\n"
            "💰 Ваш баланс: <b>{balance}</b> ✨\n\n"
            "Выберите действие на клавиатуре:"
        ),
        "start.choose_language": "🌐 <b>Выберите язык</b>",
        "lang.updated": "Язык обновлён: {lang_flag}",

        # Help
        "help.body": (
            "ℹ️ <b>Помощь</b>\n\n"
            "Команды:\n"
            "- /start — приветствие и синхронизация баланса\n"
            "- /profile — информация о пользователе и баланс\n"
            "- /generate — создать изображение по текстовому запросу\n"
            "- /topup — пополнить баланс токенов\n"
            "- /lang — выбрать язык интерфейса\n\n"
            "Примеры промптов:\n"
            "• космический нано банан, неоновая подсветка, стиль synthwave\n"
            "• реалистичный портрет нано банана, мягкий свет, 85mm, f/1.8\n"
            "• постер в стиле ретро, банан‑супергерой, зернистая текстура\n\n"
            "Советы:\n"
            "• Добавляйте стиль, освещение и композицию для лучшего результата\n"
            "• Для фото‑редактирования отправьте фото и выберите «Текст + фото 🖼️»\n"
            "• Соотношение сторон выбирается на шаге перед подтверждением\n\n"
            "Стоимость: 4 токена за изображение. Пополнение: /topup"
        ),

        # Profile
        "profile.title": "👤 <b>Профиль</b>",
        "profile.name": "Имя: {name}",
        "profile.username": "Username: {username}",
        "profile.id": "ID: {id}",
        "profile.lang": "Язык: {lang_code}",
        "profile.balance": "💰 Баланс: <b>{balance}</b> ✨",
        "profile.actions": (
            "Действия:\n"
            "• Пополнить баланс ✨ — откроет меню пополнения\n"
            "• Сгенерировать 🖼️ — запустит мастер генерации\n\n"
            "Команды: /help"
        ),

        # Topup
        "topup.title": "Пополнение токенов ✨",
        "topup.balance": "Ваш текущий баланс: <b>{balance}</b> ✨",
        "topup.choose": "Выберите сумму (1 ✨ = 1 токен):",
        "topup.method.title": "Выберите способ оплаты",
        "topup.method.sbp": "Рублями / СБП",
        "topup.method.card": "Картой (Любая страна)",
        "topup.method.old_stars": "Счёт в Telegram Stars",
        "topup.packages.title": "Выберите пакет (1 ✨ = 1 токен)",
        "topup.package.unavailable": "Оплата временно недоступна. Настройте продукты в Tribute.",
        "topup.link_hint": "Нажмите на кнопку ниже для оплаты через Tribute",
        "topup.invoice_title": "Пополнение токенов",
        "topup.invoice_desc": "Покупка {amount} токенов (Telegram Stars)",
        "topup.invoice_label": "Пополнение {amount} токенов",
        "topup.prepare": "Оформляю счёт на {amount} ✨…",
        "topup.invalid_amount": "Некорректная сумма",
        "topup.invoice_fail": "Не удалось выставить счёт. Проверьте настройки Stars у бота.",
        "topup.payment_unavailable": "Оплата недоступна. Убедитесь, что включены Telegram Stars для бота (BotFather).",
        "topup.currency_mismatch": "Оплата не в валюте XTR, обращайтесь в поддержку.",
        "topup.success": "Успешная оплата: начислено {amount} токенов. Ваш новый баланс: {balance}.\nСпасибо!",

        # Generate
        "gen.choose_method": "🪄 Выберите способ генерации:",
        "gen.type.text": "Только текст 📝",
        "gen.type.text_photo": "Текст + фото 🖼️",
        "gen.type.text_multi": "Текст + несколько фото 📷",
        "gen.type.edit_photo": "Редактировать фото ✂️",
        "gen.enter_prompt": "📝 Введите текст для генерации:",
        "gen.prompt_empty": "Пожалуйста, отправьте текстовый промпт.",
        "gen.upload_photo": "📷 Загрузите фото, которое будет использовано вместе с текстом.",
        "gen.edit.enter_prompt": "✍️ Что нужно изменить/отредактировать или добавить?",
        "gen.choose_count": "📷 <b>Выберите количество фото</b>\n\n• 1–5 в первом ряду, 6–10 во втором\n• Нажмите ‘Подтвердить ✅’ после выбора",
        "gen.use_buttons": "Пожалуйста, выберите количество фото с помощью кнопок ниже.",
        "gen.confirm_label": "Подтвердить ✅",
        "gen.confirmed_count": "✅ Выбрано: {count} фото.\n📸 Фото 1 из {count}: отправьте первое изображение.",
        "gen.photo_received": "✅ Фото {idx} из {total} получено.\n📸 Отправьте фото {next} из {total}.",
        "gen.require_photo": "📷 Пожалуйста, отправьте фото {next} из {total}.",
        "gen.choose_ratio": "📐 Выберите соотношение сторон:",
        "gen.ratio.auto": "Auto (как у исходного фото)",
        "gen.summary.title": "🔍 <b>Проверьте данные перед генерацией</b>",
        "gen.summary.type": "• Тип: {type}",
        "gen.summary.prompt": "• Промпт: {prompt}",
        "gen.summary.ratio": "• Соотношение сторон: {ratio}",
        "gen.summary.photos": "• Фото: {count} из {needed}",
        "gen.confirm.ok": "✅ Подтвердить",
        "gen.confirm.cancel": "❌ Отмена",
        "gen.canceled": "Генерация отменена.",
        "gen.not_enough_tokens": "Недостаточно токенов: требуется 4 токена за генерацию. Ваш баланс: {balance}.\nПополнить баланс: /topup",
        "gen.done_text": "Готово! Остаток токенов: {balance}\nСоотношение: {ratio}",
        "gen.result_caption": "Результат генерации",
        "gen.task_accepted": "Задача отправлена в генерацию. Результат придёт в этом чате чуть позже.",
        "gen.unknown_type": "Неизвестный тип генерации. Начните заново: /generate",
    },
    "en": {
        # Keyboard labels
        "kb.profile": "Profile 👤",
        "kb.topup": "Top up ✨",
        "kb.generate": "Generate 🖼️",

        # Start
        "start.welcome": (
            "🍌 <b>NanoBanana Bot</b>\n\n"
            "Hello, {name}! Welcome 👋\n\n"
            "✨ Features:\n"
            "• Text-to-image generation\n"
            "• Text + photo, multiple photos\n\n"
            "💳 Cost: <b>4 tokens</b> per image\n"
            "💰 Your balance: <b>{balance}</b> ✨\n\n"
            "Choose an action on the keyboard:"
        ),
        "start.choose_language": "🌐 <b>Choose your language</b>",
        "lang.updated": "Language updated: {lang_flag}",

        # Help
        "help.body": (
            "ℹ️ <b>Help</b>\n\n"
            "Commands:\n"
            "- /start — greeting and balance sync\n"
            "- /profile — user info and balance\n"
            "- /generate — create image from text prompt\n"
            "- /topup — top up tokens\n"
            "- /lang — choose interface language\n\n"
            "Prompt examples:\n"
            "• cosmic nano banana, neon glow, synthwave style\n"
            "• realistic nano banana portrait, soft light, 85mm, f/1.8\n"
            "• retro poster, banana superhero, grainy texture\n\n"
            "Tips:\n"
            "• Add style, lighting and composition for better results\n"
            "• For photo editing send a photo and choose ‘Text + photo 🖼️’\n"
            "• Aspect ratio is chosen right before confirmation\n\n"
            "Cost: 4 tokens per image. Top up: /topup"
        ),

        # Profile
        "profile.title": "👤 <b>Profile</b>",
        "profile.name": "Name: {name}",
        "profile.username": "Username: {username}",
        "profile.id": "ID: {id}",
        "profile.lang": "Language: {lang_code}",
        "profile.balance": "💰 Balance: <b>{balance}</b> ✨",
        "profile.actions": (
            "Actions:\n"
            "• Top up ✨ — opens the top‑up menu\n"
            "• Generate 🖼️ — starts the generation wizard\n\n"
            "Commands: /help"
        ),

        # Topup
        "topup.title": "Top up tokens ✨",
        "topup.balance": "Your current balance: <b>{balance}</b> ✨",
        "topup.choose": "Choose amount (1 ✨ = 1 token):",
        "topup.method.title": "Choose payment method",
        "topup.method.sbp": "Rubles / SBP",
        "topup.method.card": "Bank card (Any country)",
        "topup.method.old_stars": "Telegram Stars invoice",
        "topup.packages.title": "Choose a package (1 ✨ = 1 token)",
        "topup.package.unavailable": "Payment temporarily unavailable. Configure products in Tribute.",
        "topup.link_hint": "Tap a button below to pay via Tribute",
        "topup.invoice_title": "Top up tokens",
        "topup.invoice_desc": "Purchase {amount} tokens (Telegram Stars)",
        "topup.invoice_label": "Top up {amount} tokens",
        "topup.prepare": "Preparing invoice for {amount} ✨…",
        "topup.invalid_amount": "Invalid amount",
        "topup.invoice_fail": "Failed to send invoice. Check bot Stars settings.",
        "topup.payment_unavailable": "Payment unavailable. Ensure Telegram Stars enabled for the bot (BotFather).",
        "topup.currency_mismatch": "Payment is not in XTR currency, contact support.",
        "topup.success": "Payment successful: credited {amount} tokens. Your new balance: {balance}.\nThanks!",

        # Generate
        "gen.choose_method": "🪄 Choose generation method:",
        "gen.type.text": "Text only 📝",
        "gen.type.text_photo": "Text + photo 🖼️",
        "gen.type.text_multi": "Text + multiple photos 📷",
        "gen.type.edit_photo": "Edit photo ✂️",
        "gen.enter_prompt": "📝 Enter a prompt for generation:",
        "gen.prompt_empty": "Please send a text prompt.",
        "gen.upload_photo": "📷 Upload a photo to be used with the text.",
        "gen.edit.enter_prompt": "✍️ What should be changed/edited or added?",
        "gen.choose_count": "📷 <b>Choose number of photos</b>\n\n• 1–5 in the first row, 6–10 in the second\n• Press ‘Confirm ✅’ after choosing",
        "gen.use_buttons": "Please choose the number of photos using the buttons below.",
        "gen.confirm_label": "Confirm ✅",
        "gen.confirmed_count": "✅ Selected: {count} photos.\n📸 Photo 1 of {count}: send the first image.",
        "gen.photo_received": "✅ Photo {idx} of {total} received.\n📸 Send photo {next} of {total}.",
        "gen.require_photo": "📷 Please send photo {next} of {total}.",
        "gen.choose_ratio": "📐 Choose aspect ratio:",
        "gen.ratio.auto": "Auto (same as source photo)",
        "gen.summary.title": "🔍 <b>Review details before generation</b>",
        "gen.summary.type": "• Type: {type}",
        "gen.summary.prompt": "• Prompt: {prompt}",
        "gen.summary.ratio": "• Aspect ratio: {ratio}",
        "gen.summary.photos": "• Photos: {count} of {needed}",
        "gen.confirm.ok": "✅ Confirm",
        "gen.confirm.cancel": "❌ Cancel",
        "gen.canceled": "Generation cancelled.",
        "gen.not_enough_tokens": "Not enough tokens: 4 tokens are required. Your balance: {balance}.\nTop up: /topup",
        "gen.done_text": "Done! Balance left: {balance}\nAspect ratio: {ratio}",
        "gen.result_caption": "Generation result",
        "gen.task_accepted": "Task accepted. The result will arrive here shortly.",
        "gen.unknown_type": "Unknown generation type. Start over: /generate",
    },
}


def t(lang: str | None, key: str, **kwargs: Any) -> str:
    lang = normalize_lang(lang)
    data = STRINGS.get(lang, {})
    text = data.get(key) or STRINGS["ru"].get(key, key)
    try:
        return text.format(**kwargs)
    except Exception:
        return text