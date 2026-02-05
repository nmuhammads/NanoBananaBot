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
        "kb.avatars": "Мои аватары 👤",
        "kb.generate": "Базовая генерация 🖼️",
        "kb.nanobanana_pro": "Nanobanana Pro 🔥",
        "kb.repeat_generation": "Повторить последнюю генерацию 🔁",
        "kb.new_generation": "Новая генерация 🆕",
        "kb.start": "Старт ⏮️",
        "common.back": "🔙 Назад",

        # Start
        "start.welcome": (
            "🍌 <b>NanoBanana Bot</b>\n\n"
            "Привет, {name}! Добро пожаловать 👋\n\n"
            "✨ Возможности:\n"
            "• Генерация изображений по тексту\n"
            "• Текст + фото, несколько фото\n"
            "• Редактирование фото ✂️\n\n"
            "💳 Стоимость: базовая — <b>3 токена</b>, Pro — <b>10 токенов</b> (2K) / <b>15 токенов</b> (4K)\n"
            "💰 Ваш баланс: <b>{balance}</b> ✨\n\n"
            "Выберите действие на клавиатуре:"
        ),
        "start.choose_language": "🌐 <b>Выберите язык</b>",
        "lang.updated": "Язык обновлён: {lang_flag}",

        # Help
        "help.body": (
            "ℹ️ <b>Помощь</b>\n\n"
            "🤖 <b>Основные возможности:</b>\n"
            "• <b>NanoBanana Basic</b> — быстрая генерация (3 токена).\n"
            "• <b>NanoBanana Pro</b> — высокое качество 2K/4K (10/15 токенов).\n"
            "• <b>Аватары 👤</b> — сохраните персонажа, чтобы использовать его в генерациях (Текст + Фото/Мульти).\n"
            "• <b>Мульти-фото</b> — используйте несколько референсов или аватаров одновременно.\n\n"
            "📜 <b>Команды:</b>\n"
            "- /start — перезапустить бота\n"
            "- /profile — профиль и баланс\n"
            "- /avatars — управление вашими аватарами\n"
            "- /generate — меню генерации\n"
            "- /topup — пополнить баланс\n"
            "- /prices — цены\n"
            "- /lang — смена языка\n\n"
            "💡 <b>Советы:</b>\n"
            "• Используйте кнопку <b>«Мои аватары 👤»</b> в меню для быстрой настройки персонажей.\n"
            "• В режиме «Текст + фото» можно выбрать сохраненный аватар вместо загрузки фото.\n"
            "• Для Pro-режима доступны разные разрешения (Square, Youtube, Portrait).\n\n"
            "💎 <b>Стоимость:</b>\n"
            "Basic: 3 🍌\n"
            "Pro 2K: 10 🍌\n"
            "Pro 4K: 15 🍌\n"
        ),

        # Avatars
        "avatars.title": "👤 <b>Мои аватары</b>",
        "avatars.add": "➕ Добавить аватар",
        "avatars.empty": "У вас пока нет сохранённых аватаров. Добавьте первый, чтобы использовать его в генерациях!",
        "avatars.delete_hint": "Нажмите на кнопку с именем аватара, чтобы удалить его.",
        "avatars.upload_photo": "📸 Отправьте фото для аватара.",
        "avatars.enter_name": "✍️ Введите название для этого аватара (до 30 символов).",
        "avatars.saved": "✅ Аватар <b>{name}</b> сохранён!",
        "avatars.deleted": "🗑️ Аватар удалён.",
        "avatars.choose_source": "Вы хотите использовать сохранённый аватар или загрузить новое фото?",
        "avatars.source_photo": "📷 Загрузить фото",
        "avatars.source_avatar": "👤 Выбрать аватар",
        "avatars.pick_hint": "Выберите аватар из списка:",
        "avatars.pick_multi_hint": "Выберите до 10 аватаров (отметьте нужные галочками), затем нажмите «Подтвердить».",
        "avatars.confirm_selection": "✅ Подтвердить выбор ({count})",
        "avatars.max_selected": "Максимум 10 аватаров!",
        "avatars.btn_label": "Мои аватары 👤",

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
            "• Базовая генерация 🖼️ — 3 токена\n"
            "• Nanobanana Pro 🔥 — 10/15 токенов (2K/4K)\n\n"
            "Команды: /help"
        ),

        # Topup
        "topup.title": "Пополнение токенов ✨",
        "topup.balance": "Ваш текущий баланс: <b>{balance}</b> ✨",
        "topup.choose": "Выберите сумму (1 ✨ = 1 токен):",
        "topup.method.title": "Выберите способ оплаты",
        "topup.method.sbp": "🏦 Рублями / СБП",
        "topup.method.card": "💳 Картой (Любая страна)",
        "topup.method.old_stars": "⭐ Счёт в Telegram Stars",
        "topup.method.bonus": "Купить с бонусом +15% к токенам",
        "topup.bonus_info": "🔥 <b>Бонус +15%</b> при покупке через администратора (от 200 токенов)!",
        "topup.packages.title": "2 звезды = 1 токен",
        "topup.package.unavailable": "Оплата временно недоступна. Настройте продукты в Tribute.",
        "topup.link_hint": "",
        "topup.invoice_title": "Пополнение токенов",
        "topup.invoice_desc": "Покупка {amount} токенов (Telegram Stars)",
        "topup.invoice_label": "Пополнение {amount} токенов ✨",
        "topup.prepare": "Оформляю счёт на {amount} ✨…",
        "topup.invalid_amount": "Некорректная сумма",
        "topup.invoice_fail": "Не удалось выставить счёт. Проверьте настройки Stars у бота.",
        "topup.payment_unavailable": "Оплата недоступна. Убедитесь, что включены Telegram Stars для бота (BotFather).",
        "topup.currency_mismatch": "Оплата не в валюте XTR, обращайтесь в поддержку.",
        "topup.success": "Успешная оплата: начислено {amount} токенов. Ваш новый баланс: {balance}.\nСпасибо!",

        # Prices
        "prices.title": "📋 Цены на токены",
        "prices.rubles.header": "💳 Оплата рублями (СБП / карта):",
        "prices.usd.header": "💳 Оплата в долларах (карта):",
        "prices.stars.header": "✨ Оплата звёздами:",
        "prices.stars.line": "1 токен = 1 ✨ (без комиссии)",
        "prices.disclaimer": "ℹ️ Платёжный сервис может брать комиссию; итоговая стоимость может немного отличаться. Оплата звёздами — без комиссии.",

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
        "gen.how_many_photos": "📷 <b>Сколько фото вы хотите использовать?</b>\n\nВыберите количество от 1 до 10:",
        "gen.choose_count": "📷 <b>Выберите количество фото</b>\n\n• 1–5 в первом ряду, 6–10 во втором\n• Нажмите 'Подтвердить ✅' после выбора",
        "gen.use_buttons": "Пожалуйста, выберите количество фото с помощью кнопок ниже.",
        "gen.confirm_label": "Подтвердить ✅",
        "gen.confirmed_count": "✅ Выбрано: {count} фото.\n📸 Фото 1 из {count}: отправьте первое изображение.",
        "gen.photo_received": "✅ Фото {idx} из {total} получено.\n📸 Отправьте фото {next} из {total}.",
        "gen.require_photo": "📷 Пожалуйста, отправьте фото {next} из {total}.",
        "gen.choose_ratio": "📐 Выберите соотношение сторон:",
        "gen.choose_resolution": "📐 Выберите разрешение:",
        "gen.ratio.auto": "Auto (как у исходного фото)",
        "gen.summary.title": "🔍 <b>Проверьте данные перед генерацией</b>",
        "gen.summary.type": "• Тип: {type}",
        "gen.summary.prompt": "• Промпт: {prompt}",
        "gen.summary.ratio": "• Соотношение сторон: {ratio}",
        "gen.summary.resolution": "• Разрешение: {resolution} ({price} 🍌)",
        "gen.summary.photos": "• Фото: {count} из {needed}",
        "gen.confirm.ok": "✅ Подтвердить",
        "gen.confirm.cancel": "❌ Отмена",
        "gen.canceled": "Генерация отменена.",
        "gen.not_enough_tokens": "Недостаточно токенов: требуется {required} токенов. Ваш баланс: {balance}.\nПополнить баланс: /topup",
        "gen.done_text": "Готово! Остаток токенов: {balance}\nСоотношение: {ratio}",
        "gen.result_caption": "Результат генерации",
        "gen.task_accepted": "Задача отправлена в генерацию. Результат придёт в этом чате чуть позже.",
        "gen.unknown_type": "Неизвестный тип генерации. Начните заново: /generate",
        "gen.repeat_not_found": "Повтор невозможен: нет предыдущей генерации.",
        "gen.repeat_unsupported": "Повтор работает только для текстовых генераций без изображений.",
    },
    "en": {
        # Keyboard labels
        "kb.profile": "Profile 👤",
        "kb.topup": "Top up ✨",
        "kb.avatars": "My Avatars 👤",
        "kb.generate": "Basic generation 🖼️",
        "kb.nanobanana_pro": "Nanobanana Pro 🔥",
        "kb.repeat_generation": "Repeat last generation 🔁",
        "kb.new_generation": "New generation 🆕",
        "kb.start": "Start ⏮️",
        "common.back": "🔙 Back",

        # Start
        "start.welcome": (
            "🍌 <b>NanoBanana Bot</b>\n\n"
            "Hello, {name}! Welcome 👋\n\n"
            "✨ Features:\n"
            "• Text-to-image generation\n"
            "• Text + photo, multiple photos\n"
            "• Edit photo ✂️\n\n"
            "💳 Cost: basic — <b>3 tokens</b>, Pro — <b>10 tokens</b> (2K) / <b>15 tokens</b> (4K)\n"
            "💰 Your balance: <b>{balance}</b> ✨\n\n"
            "Choose an action on the keyboard:"
        ),
        "start.choose_language": "🌐 <b>Choose your language</b>",
        "lang.updated": "Language updated: {lang_flag}",

        # Help
        "help.body": (
            "ℹ️ <b>Help</b>\n\n"
            "🤖 <b>Key Features:</b>\n"
            "• <b>NanoBanana Basic</b> — fast generation (3 tokens).\n"
            "• <b>NanoBanana Pro</b> — high quality 2K/4K (10/15 tokens).\n"
            "• <b>Avatars 👤</b> — save a character to reuse in generations (Text + Photo/Multi).\n"
            "• <b>Multi-photo</b> — use multiple references or avatars at once.\n\n"
            "📜 <b>Commands:</b>\n"
            "- /start — restart bot\n"
            "- /profile — profile & balance\n"
            "- /avatars — manage your avatars\n"
            "- /generate — generation menu\n"
            "- /topup — top up balance\n"
            "- /prices — token prices\n"
            "- /lang — change language\n\n"
            "💡 <b>Tips:</b>\n"
            "• Use <b>'My Avatars 👤'</b> button for quick character setup.\n"
            "• In 'Text + Photo' mode, you can pick a saved avatar instead of uploading.\n"
            "• Pro mode supports various aspect ratios (Square, Youtube, Portrait).\n\n"
            "💎 <b>Cost:</b>\n"
            "Basic: 3 🍌\n"
            "Pro 2K: 10 🍌\n"
            "Pro 4K: 15 🍌\n"
        ),

        # Avatars
        "avatars.title": "👤 <b>My Avatars</b>",
        "avatars.add": "➕ Add Avatar",
        "avatars.empty": "You don't have saved avatars yet. Add one to use in generations!",
        "avatars.delete_hint": "Press the button with avatar name to delete it.",
        "avatars.upload_photo": "📸 Send a photo for the avatar.",
        "avatars.enter_name": "✍️ Enter a name for this avatar (max 30 chars).",
        "avatars.saved": "✅ Avatar <b>{name}</b> saved!",
        "avatars.deleted": "🗑️ Avatar deleted.",
        "avatars.choose_source": "Do you want to use a saved avatar or upload a new photo?",
        "avatars.source_photo": "📷 Upload Photo",
        "avatars.source_avatar": "👤 Choose Avatar",
        "avatars.pick_hint": "Choose an avatar from the list:",
        "avatars.pick_multi_hint": "Select up to 10 avatars (check them), then press 'Confirm'.",
        "avatars.confirm_selection": "✅ Confirm Selection ({count})",
        "avatars.max_selected": "Maximum 10 avatars!",
        "avatars.btn_label": "My Avatars 👤",

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
            "• Basic generation 🖼️ — 3 tokens\n"
            "• Nanobanana Pro 🔥 — 10/15 tokens (2K/4K)\n\n"
            "Commands: /help"
        ),

        # Topup
        "topup.title": "Top up tokens ✨",
        "topup.balance": "Your current balance: <b>{balance}</b> ✨",
        "topup.choose": "Choose amount (1 ✨ = 1 token):",
        "topup.method.title": "Choose payment method",
        "topup.method.sbp": "🏦 Rubles / SBP",
        "topup.method.card": "💳 Bank card (Any country)",
        "topup.method.old_stars": "⭐ Telegram Stars invoice",
        "topup.method.bonus": "Buy with +15% token bonus",
        "topup.bonus_info": "🔥 <b>+15% Bonus</b> when buying via admin (min 200 tokens)!",
        "topup.packages.title": "2 Stars = 1 token",
        "topup.package.unavailable": "Payment temporarily unavailable. Configure products in Tribute.",
        "topup.link_hint": "",
        "topup.invoice_title": "Top up tokens",
        "topup.invoice_desc": "Purchase {amount} tokens (Telegram Stars)",
        "topup.invoice_label": "Top up {amount} tokens ✨",
        "topup.prepare": "Preparing invoice for {amount} ✨…",
        "topup.invalid_amount": "Invalid amount",
        "topup.invoice_fail": "Failed to send invoice. Check bot Stars settings.",
        "topup.payment_unavailable": "Payment unavailable. Ensure Telegram Stars enabled for the bot (BotFather).",
        "topup.currency_mismatch": "Payment is not in XTR currency, contact support.",
        "topup.success": "Payment successful: credited {amount} tokens. Your new balance: {balance}.\nThanks!",

        # Prices
        "prices.title": "📋 Token prices",
        "prices.rubles.header": "💳 Pay in rubles (SBP / card):",
        "prices.usd.header": "💳 Pay in USD (card):",
        "prices.stars.header": "✨ Pay with Stars:",
        "prices.stars.line": "1 token = 1 ✨ (no commission)",
        "prices.disclaimer": "ℹ️ Payment service may charge a commission; final price may slightly differ. Stars payments are commission‑free.",

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
        "gen.how_many_photos": "📷 <b>How many photos do you want to use?</b>\n\nChoose a number from 1 to 10:",
        "gen.choose_count": "📷 <b>Choose number of photos</b>\n\n• 1–5 in the first row, 6–10 in the second\n• Press 'Confirm ✅' after choosing",
        "gen.use_buttons": "Please choose the number of photos using the buttons below.",
        "gen.confirm_label": "Confirm ✅",
        "gen.confirmed_count": "✅ Selected: {count} photos.\n📸 Photo 1 of {count}: send the first image.",
        "gen.photo_received": "✅ Photo {idx} of {total} received.\n📸 Send photo {next} of {total}.",
        "gen.require_photo": "📷 Please send photo {next} of {total}.",
        "gen.choose_ratio": "📐 Choose aspect ratio:",
        "gen.choose_resolution": "📐 Choose resolution:",
        "gen.ratio.auto": "Auto (same as source photo)",
        "gen.summary.title": "🔍 <b>Review details before generation</b>",
        "gen.summary.type": "• Type: {type}",
        "gen.summary.prompt": "• Prompt: {prompt}",
        "gen.summary.ratio": "• Aspect ratio: {ratio}",
        "gen.summary.resolution": "• Resolution: {resolution} ({price} 🍌)",
        "gen.summary.photos": "• Photos: {count} of {needed}",
        "gen.confirm.ok": "✅ Confirm",
        "gen.confirm.cancel": "❌ Cancel",
        "gen.canceled": "Generation cancelled.",
        "gen.not_enough_tokens": "Insufficient tokens: requires {required} tokens. Your balance: {balance}.\nTop up: /topup",
        "gen.done_text": "Done! Balance left: {balance}\nAspect ratio: {ratio}",
        "gen.result_caption": "Generation result",
        "gen.task_accepted": "Task accepted. The result will arrive here shortly.",
        "gen.unknown_type": "Unknown generation type. Start over: /generate",
        "gen.repeat_not_found": "Cannot repeat: no previous generation found.",
        "gen.repeat_unsupported": "Repeat only supported for text-only generations.",
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
