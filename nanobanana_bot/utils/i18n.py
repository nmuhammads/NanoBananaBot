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
        "kb.avatars": "Мои аватары 📸",
        "kb.new_generation": "Новая генерация 🖼️",
        "kb.repeat_generation": "Повторить генерацию 🔁",
        "kb.seedream_4_5": "Seedream 4.5 🔥",

        # Model selection
        "gen.choose_model": "Выберите модель для генерации:",
        "gen.model.v4": "Seedream 4 (4 🪙)",
        "gen.model.v4_5": "Seedream 4.5 (7 🪙)",
        "kb.start": "Главное меню",

        # Start
        "start.welcome": (
        "✨ <b>Seedream Bot</b>\n\n"
            "Привет, {name}! Добро пожаловать 👋\n\n"
            "✨ Возможности:\n"
            "• Текст + Фото/Аватар ✨\n"
            "• Текст + несколько фото/Аватаров ✨ (до 5)\n"
            "• Редактирование фото ✂️\n"
            "• Мои аватары: добавление и удаление 📸\n\n"
            "💳 Стоимость:\n"
            "• Seedream 4: 4 токена\n"
            "• Seedream 4.5: 7 токенов\n"
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
            "- /avatars — управление аватарами\n"
            "- /topup — пополнить баланс токенов\n"
            "- /prices — цены на токены\n"
            "- /lang — выбрать язык интерфейса\n\n"
            "Новое:\n"
            "• «Текст + Фото/Аватар ✨» — отправьте фото или выберите аватар\n"
            "• «Текст + несколько фото/Аватаров ✨» — отметьте до 5 аватаров на шаге «➕ Добавить аватары»\n"
            "• В /avatars добавляйте и удаляйте аватары (удаление с подтверждением)\n\n"
            "Как пользоваться:\n"
            "1) Выберите режим в /generate\n"
            "2) Введите промпт\n"
            "3) Для «Фото/Аватар» — отправьте фото или выберите аватар\n"
            "4) Для «несколько фото/Аватаров» — выберите количество или добавьте аватары, подтвердите\n"
            "5) Выберите соотношение сторон и подтвердите задачу\n\n"
            "Примеры промптов:\n"
            "• космический нано банан, неоновая подсветка, стиль synthwave\n"
            "• реалистичный портрет нано банана, мягкий свет, 85mm, f/1.8\n"
            "• постер в стиле ретро, банан‑супергерой, зернистая текстура\n\n"
            "Советы:\n"
            "• Добавляйте стиль, освещение и композицию для лучшего результата\n"
            "• Для фото‑редактирования отправьте фото и выберите «Редактировать фото ✂️»\n"
            "• Соотношение сторон выбирается перед подтверждением\n\n"
            "Стоимость:\n• Seedream 4: 4 токена\n• Seedream 4.5: 7 токенов\nПополнение: /topup"
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
        "topup.choose": "Выберите сумму (2 ✨ = 1 токен):",
        "topup.method.title": "Выберите способ оплаты",
        "topup.method.sbp": "Рублями / СБП",
        "topup.method.card": "Картой (Любая страна)",
        "topup.method.old_stars": "Счёт в Telegram Stars",
        "topup.packages.title": "Выберите пакет (2 ✨ = 1 токен)",
        "topup.package.unavailable": "Оплата временно недоступна. Настройте продукты в Tribute.",
        "topup.link_hint": "Нажмите на кнопку ниже для оплаты.",
        "topup.invoice_title": "Пополнение токенов",
        "topup.invoice_desc": "Покупка {amount} токенов (Telegram Stars)",
        "topup.invoice_label": "Пополнение {amount} токенов",
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
        "prices.stars.line": "1 токен = 2 ✨ (без комиссии)",
        "prices.disclaimer": "ℹ️ Платёжный сервис может брать комиссию; итоговая стоимость может немного отличаться. Оплата звёздами — без комиссии.",

        # Generate
        "gen.choose_method": "🪄 <b>Выберите режим</b>",
        "gen.type.text": "Текст (Только промпт) ✨",
        "gen.type.text_photo": "Текст + Фото/Аватар ✨",
        "gen.type.text_multi": "Текст + несколько фото/Аватаров ✨",
        "gen.type.edit_photo": "Редактировать фото ✂️",
        "gen.enter_prompt": "📝 Опишите идею для изображения",
        # Short placeholders for input fields
        "ph.prompt": "Опишите идею…",
        "ph.edit_prompt": "Что изменить?",
        "gen.prompt_empty": "Пожалуйста, отправьте текстовый промпт.",
        "gen.upload_photo": "📷 Добавьте фото, которое учитывается при генерации.",
        "gen.edit.enter_prompt": "✍️ Что изменить в фото?",
        "gen.choose_count": "📷 <b>Выберите количество фото</b>\n\n• 1–5 в первом ряду, 6–10 во втором\n• Нажмите ‘Запустить ✅’",
        "gen.btn.add_avatars": "➕ Добавить аватары",
        "gen.use_buttons": "Пожалуйста, выберите количество фото с помощью кнопок ниже.",
        "gen.confirm_label": "Запустить ✅",
        "gen.confirmed_count": "✅ Выбрано: {count} фото.\n📸 Фото 1 из {count}: отправьте первое изображение.",
        "gen.photo_received": "✅ Фото {idx} из {total} получено.\n📸 Отправьте фото {next} из {total}.",
        "gen.require_photo": "📷 Пожалуйста, отправьте фото {next} из {total}.",
        "gen.choose_ratio": (
            "📐 <b>Ориентация и соотношение</b>\n\n"
            "◻️ Квадрат: 1:1\n"
            "📱 Портрет: 3:4, 2:3, 9:16\n"
            "🖼️ Альбом: 4:3, 3:2, 16:9, 21:9"
        ),
        "gen.ratio.auto": "Auto (как у исходного фото)",
        "gen.summary.title": "🔍 <b>Проверьте детали</b>",
        "gen.summary.type": "• Тип: {type}",
        "gen.summary.prompt": "• Промпт: {prompt}",
        "gen.summary.ratio": "• Соотношение сторон: {ratio}",
        "gen.summary.photos": "• Фото: {count} из {needed}",
        "gen.summary.avatar": "• Аватар: {name}",
        "gen.summary.avatars": "• Аватары: {names}",
        "gen.confirm.ok": "✅ Подтвердить",
        "gen.confirm.cancel": "❌ Отмена",
        "gen.canceled": "Генерация отменена.",
        "gen.not_enough_tokens": "Нужно {price} токенов. Ваш баланс: {balance}.\nПополнить: /topup",
        "gen.done_text": "✨ Готово! Остаток: {balance}\nСоотношение: {ratio}",
        "gen.failed.generic": "Не удалось запустить генерацию. Попробуйте позже. Токены возвращены.",
        "gen.failed.max_length": "⚠️ Ошибка: Длина запроса превышает лимит (максимум 1000 символов). Пожалуйста, сократите текст.",
        "gen.task_accepted": "Задача принята в обработку! Ожидайте результат... скоро будет здесь ✨",
        "gen.repeat_not_found": "Нет недавней успешной генерации для повторения.",
        # Failure handling
        "gen.failed.prompt_too_long": (
            "❗️ Промпт слишком длинный. Максимум 2500 символов.\n"
            "Возврат 3 токенов. Баланс: {balance}\n"
            "Сократите текст и попробуйте снова."
        ),
            "❗️ Генерация не удалась. Причина: {reason}.\n"
            "Возврат средств. Баланс: {balance}"
        "gen.unknown_type": "Неизвестный тип генерации. Начните заново: /generate",
        
        # Avatars
        "avatars.title": "📸 <b>Мои аватары</b>",
        "avatars.add": "➕ Добавить аватар",
        "avatars.empty": "У вас пока нет аватаров. Добавьте первый!",
        "avatars.prompt_photo": "📷 Отправьте фото для аватара",
        "avatars.prompt_name": "📝 Введите название (отображаемое имя) для аватара",
        "avatars.ph_name": "Например: Портрет в студии",
        "avatars.name_empty": "Пожалуйста, введите название аватара.",
        "avatars.saved": "✅ Аватар «{name}» сохранён",
        "avatars.error_upload": "Не удалось сохранить аватар. Попробуйте позже.",
        "avatars.error_delete": "Не удалось удалить аватар.",
        "avatars.deleted": "Удалено",
        "avatars.choose_source": "Хотите сгенерировать фото, используя Фото или ваш Аватар?",
        "avatars.btn_send_new": "📤 Отправить новое фото",
        "avatars.btn_choose": "📚 Выбрать аватар",
        "avatars.pick_title": "Выберите аватар из списка:",
        "avatars.pick_multi_title": "Выберите аватары (до 5):",
        "avatars.multi.limit_reached": "Можно выбрать до 5 аватаров.",
        "avatars.error_pick": "Не удалось выбрать аватар. Попробуйте снова.",
        "avatars.delete_hint": "ℹ️ Нажмите на аватар, чтобы удалить. Появится подтверждение.",
        "avatars.confirm_delete": "Удалить аватар «{name}»? Это действие необратимо.",
        "avatars.btn_delete": "🗑️ Удалить",
        "avatars.add.cancel_hint": "Нажмите «Отмена» ниже, чтобы отменить добавление.",
    },
    "en": {
        # Keyboard labels
        "kb.profile": "Profile 👤",
        "kb.topup": "Top up ✨",
        "kb.generate": "Generate 🖼️",
        "kb.avatars": "My Avatars 📸",
        "kb.new_generation": "New generation 🖼️",
        "kb.repeat_generation": "Repeat generation 🔁",
        "kb.seedream_4_5": "Seedream 4.5 🔥",

        # Model selection
        "gen.choose_model": "Choose a generation model:",
        "gen.model.v4": "Seedream 4 (4 🪙)",
        "gen.model.v4_5": "Seedream 4.5 (7 🪙)",
        "kb.start": "Main menu",

        # Start
        "start.welcome": (
        "✨ <b>Seedream Bot</b>\n\n"
            "Hello, {name}! Welcome 👋\n\n"
            "✨ Features:\n"
            "• Text + Photo/Avatar ✨\n"
            "• Text + Multiple Photos/Avatars ✨ (up to 5)\n"
            "• Edit photo ✂️\n"
            "• Manage avatars: add & delete 📸\n\n"
            "💳 Cost:\n"
            "• Seedream 4: 4 tokens\n"
            "• Seedream 4.5: 7 tokens\n"
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
            "- /avatars — manage avatars\n"
            "- /topup — top up tokens\n"
            "- /prices — token prices\n"
            "- /lang — choose interface language\n\n"
            "New:\n"
            "• ‘Text + Photo/Avatar ✨’ — send a photo or pick an avatar\n"
            "• ‘Text + Multiple Photos/Avatars ✨’ — pick up to 5 avatars via ‘➕ Add avatars’\n"
            "• /avatars lets you add and delete avatars (with confirmation)\n\n"
            "How to use:\n"
            "1) Choose a mode in /generate\n"
            "2) Enter a prompt\n"
            "3) For ‘Photo/Avatar’ — send a photo or pick an avatar\n"
            "4) For ‘Multiple Photos/Avatars’ — choose count or add avatars, then confirm\n"
            "5) Choose aspect ratio and confirm the task\n\n"
            "Prompt examples:\n"
            "• cosmic nano banana, neon glow, synthwave style\n"
            "• realistic nano banana portrait, soft light, 85mm, f/1.8\n"
            "• retro poster, banana superhero, grainy texture\n\n"
            "Tips:\n"
            "• Add style, lighting and composition for better results\n"
            "• For photo editing send a photo and choose ‘Edit Photo ✂️’\n"
            "• Aspect ratio is chosen right before confirmation\n\n"
            "Cost:\n• Seedream 4: 4 tokens\n• Seedream 4.5: 7 tokens\nTop up: /topup"
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
        "topup.choose": "Choose amount (2 ✨ = 1 token):",
        "topup.method.title": "Choose payment method",
        "topup.method.sbp": "Rubles / SBP",
        "topup.method.card": "Bank card (Any country)",
        "topup.method.old_stars": "Telegram Stars invoice",
        "topup.packages.title": "Choose a package (2 ✨ = 1 token)",
        "topup.package.unavailable": "Payment temporarily unavailable. Configure products in Tribute.",
        "topup.link_hint": "Tap a button below to pay.",
        "topup.invoice_title": "Top up tokens",
        "topup.invoice_desc": "Purchase {amount} tokens (Telegram Stars)",
        "topup.invoice_label": "Top up {amount} tokens",
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
        "prices.stars.line": "1 token = 2 ✨ (no commission)",
        "prices.disclaimer": "ℹ️ Payment service may charge a commission; final price may slightly differ. Stars payments are commission‑free.",

        # Generate
        "gen.choose_method": "🪄 <b>Choose a mode</b>",
        "gen.type.text": "Text (Prompt only) ✨",
        "gen.type.text_photo": "Text + Photo/Avatar ✨",
        "gen.type.text_multi": "Text + Multiple Photos/Avatars ✨",
        "gen.type.edit_photo": "Edit Photo ✂️",
        "gen.enter_prompt": "📝 Describe your idea",
        # Short placeholders for input fields
        "ph.prompt": "Describe your idea…",
        "ph.edit_prompt": "What to change?",
        "gen.prompt_empty": "Please send a text prompt.",
        "gen.upload_photo": "📷 Attach a photo to guide generation.",
        "gen.edit.enter_prompt": "✍️ What should be changed or added?",
        "gen.choose_count": "📷 <b>Choose number of photos</b>\n\n• 1–5 in the first row, 6–10 in the second\n• Press ‘Launch ✅’",
        "gen.btn.add_avatars": "➕ Add Avatars",
        "gen.use_buttons": "Please choose the number of photos using the buttons below.",
        "gen.confirm_label": "Launch ✅",
        "gen.confirmed_count": "✅ Selected: {count} photos.\n📸 Photo 1 of {count}: send the first image.",
        "gen.photo_received": "✅ Photo {idx} of {total} received.\n📸 Send photo {next} of {total}.",
        "gen.require_photo": "📷 Please send photo {next} of {total}.",
        "gen.choose_ratio": (
            "📐 <b>Choose orientation & aspect</b>\n\n"
            "◻️ Square: 1:1\n"
            "📱 Portrait: 3:4, 2:3, 9:16\n"
            "🖼️ Landscape: 4:3, 3:2, 16:9, 21:9"
        ),
        "gen.ratio.auto": "Auto (same as source photo)",
        "gen.summary.title": "🔍 <b>Review details</b>",
        "gen.summary.type": "• Type: {type}",
        "gen.summary.prompt": "• Prompt: {prompt}",
        "gen.summary.ratio": "• Aspect ratio: {ratio}",
        "gen.summary.photos": "• Photos: {count} of {needed}",
        "gen.summary.avatar": "• Avatar: {name}",
        "gen.summary.avatars": "• Avatars: {names}",
        "gen.confirm.ok": "✅ Confirm",
        "gen.confirm.cancel": "❌ Cancel",
        "gen.canceled": "Generation cancelled.",
        "gen.not_enough_tokens": "Needs {price} tokens. Your balance: {balance}.\nTop up: /topup",
        "gen.done_text": "✨ Done! Balance left: {balance}\nAspect ratio: {ratio}",
        "gen.failed.generic": "Failed to start generation. Please try again later. Tokens refunded.",
        "gen.failed.max_length": "⚠️ Error: Prompt length exceeds the limit (max 1000 characters). Please shorten your text.",
        "gen.task_accepted": "Task sent to bot. The result will arrive here shortly.",
        "gen.repeat_not_found": "No recent successful generation to repeat.",
        # Failure handling
        "gen.failed.prompt_too_long": (
            "❗️ Prompt too long. Max 2500 characters.\n"
            "Refunded 3 tokens. Balance: {balance}\n"
            "Please shorten the prompt and try again."
        ),
            "❗️ Generation failed. Reason: {reason}.\n"
            "Refunded. Balance: {balance}"
        "gen.unknown_type": "Unknown generation type. Start over: /generate",

        # Avatars
        "avatars.title": "📸 <b>My Avatars</b>",
        "avatars.add": "➕ Add avatar",
        "avatars.empty": "You don't have avatars yet. Add one!",
        "avatars.prompt_photo": "📷 Send a photo for the avatar",
        "avatars.prompt_name": "📝 Enter a display name for the avatar",
        "avatars.ph_name": "e.g. Studio portrait",
        "avatars.name_empty": "Please enter an avatar name.",
        "avatars.saved": "✅ Avatar “{name}” saved",
        "avatars.error_upload": "Failed to save avatar. Please try later.",
        "avatars.error_delete": "Failed to delete avatar.",
        "avatars.deleted": "Deleted",
        "avatars.choose_source": "Would you like to generate using a Photo or your Avatar?",
        "avatars.btn_send_new": "📤 Send a new photo",
        "avatars.btn_choose": "📚 Choose avatar",
        "avatars.pick_title": "Select an avatar from the list:",
        "avatars.pick_multi_title": "Choose avatars (up to 5):",
        "avatars.multi.limit_reached": "You can select up to 5 avatars.",
        "avatars.error_pick": "Failed to pick avatar. Please try again.",
        "avatars.delete_hint": "ℹ️ Tap an avatar to delete. A confirmation will appear.",
        "avatars.confirm_delete": "Delete avatar “{name}”? This action cannot be undone.",
        "avatars.btn_delete": "🗑️ Delete",
        "avatars.add.cancel_hint": "Tap ‘Cancel’ below to abort adding.",
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
