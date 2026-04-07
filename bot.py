import os
import json
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
DB_FILE = "db.json"

(ASKING_CLASS, ASKING_REGION, ASKING_BUDGET, ASKING_TEST, FREE_CHAT) = range(5)
(ADMIN_PASSWORD_INPUT, ADMIN_MENU, ADMIN_BROADCAST, ADMIN_BAN, ADMIN_UNBAN,
 ADMIN_CHAT, ADMIN_PROMPT_EDIT, ADMIN_USER_INFO) = range(5, 13)

QUESTIONS = [
    "Что тебе больше нравится?\n\nА) Работать с людьми\nБ) Работать с техникой/компьютерами\nВ) Работать с природой/животными\nГ) Работать с текстами/творчеством",
    "Как проводишь свободное время?\n\nА) Общаюсь с друзьями, организую мероприятия\nБ) Играю в игры, программирую, собираю что-то\nВ) Провожу время на природе, занимаюсь спортом\nГ) Рисую, пишу, слушаю музыку",
    "Какой предмет даётся легче всего?\n\nА) История, обществознание, литература\nБ) Математика, физика, информатика\nВ) Биология, химия, география\nГ) Русский язык, ИЗО, музыка",
    "Каким видишь себя через 10 лет?\n\nА) Помогаю людям, работаю в команде\nБ) Создаю технологии, решаю сложные задачи\nВ) Работаю на свежем воздухе, занимаюсь исследованиями\nГ) Занимаюсь творчеством, создаю что-то уникальное",
    "Что важнее в работе?\n\nА) Общение и помощь другим\nБ) Логика и точность\nВ) Физическая активность и природа\nГ) Свобода и самовыражение",
    "Как принимаешь решения?\n\nА) Советуюсь с другими, учитываю чувства людей\nБ) Анализирую факты и логически размышляю\nВ) Доверяю интуиции и практическому опыту\nГ) Слушаю своё сердце и творческий импульс",
    "Какой тип задач нравится?\n\nА) Организовывать людей и процессы\nБ) Решать технические и математические задачи\nВ) Исследовать и экспериментировать\nГ) Создавать и придумывать новое",
    "Что больше всего раздражает?\n\nА) Когда люди не могут договориться\nБ) Когда что-то работает неправильно и непонятно почему\nВ) Когда приходится сидеть в офисе весь день\nГ) Когда нет места для творчества и инициативы",
]

DEFAULT_SYSTEM_PROMPT = """Ты крутой профориентационный эксперт для школьников. Отвечай ТОЛЬКО на русском языке.

Стиль: живой, дружелюбный, как старший друг а не учитель. Без занудства и канцелярита.
Длина: коротко — 3-4 предложения максимум.
Честность: если профессия не подходит человеку — говори прямо, без сюсюканья.
Тема: только профессии, образование, карьера. На остальное вежливо отказывай.
Учебные заведения: только реальные, которые точно существуют."""


# ===== БД =====

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "system_prompt": DEFAULT_SYSTEM_PROMPT, "profession_stats": {}, "total_messages": 0}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def register_user(user_id, username, first_name):
    db = load_db()
    uid = str(user_id)
    now = datetime.now().isoformat()
    if uid not in db["users"]:
        db["users"][uid] = {
            "username": username or "",
            "first_name": first_name or "",
            "joined": now,
            "tests_completed": 0,
            "messages_sent": 0,
            "banned": False,
            "last_active": now,
            "grade": "",
            "region": "",
        }
    else:
        db["users"][uid]["last_active"] = now
        db["users"][uid]["username"] = username or ""
        db["users"][uid]["first_name"] = first_name or ""
    save_db(db)

def is_banned(user_id):
    db = load_db()
    return db["users"].get(str(user_id), {}).get("banned", False)

def increment_tests(user_id, grade="", region=""):
    db = load_db()
    uid = str(user_id)
    if uid in db["users"]:
        db["users"][uid]["tests_completed"] = db["users"][uid].get("tests_completed", 0) + 1
        if grade:
            db["users"][uid]["grade"] = grade
        if region:
            db["users"][uid]["region"] = region
    save_db(db)

def increment_messages(user_id):
    db = load_db()
    uid = str(user_id)
    if uid in db["users"]:
        db["users"][uid]["messages_sent"] = db["users"][uid].get("messages_sent", 0) + 1
    db["total_messages"] = db.get("total_messages", 0) + 1
    save_db(db)

def add_profession_stat(profession):
    db = load_db()
    db["profession_stats"][profession] = db["profession_stats"].get(profession, 0) + 1
    save_db(db)

def get_system_prompt():
    return load_db().get("system_prompt", DEFAULT_SYSTEM_PROMPT)

def set_system_prompt(prompt):
    db = load_db()
    db["system_prompt"] = prompt
    save_db(db)

def ban_user(identifier, ban=True):
    db = load_db()
    identifier = identifier.lstrip("@")
    for uid, u in db["users"].items():
        if u.get("username") == identifier or uid == identifier:
            db["users"][uid]["banned"] = ban
            save_db(db)
            return u.get("username") or uid
    return None

def get_user_info(identifier):
    db = load_db()
    identifier = identifier.lstrip("@")
    for uid, u in db["users"].items():
        if u.get("username") == identifier or uid == identifier:
            return uid, u
    return None, None


# ===== АПИ =====

def ai_request(messages):
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "nvidia/nemotron-3-super-120b-a12b:free",
            "messages": messages
        },
        timeout=60
    )
    return response.json()["choices"][0]["message"]["content"]


# ===== ОБЫЧНЫЙ БОТ =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.username, user.first_name)

    if is_banned(user.id):
        await update.message.reply_text("Ты заблокирован в этом боте.")
        return ConversationHandler.END

    context.user_data.clear()

    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Помогу разобраться с выбором профессии — быстро и без воды.\n\n"
        "Сначала пара вопросов, потом тест из 8 шагов. В каком ты классе?",
        reply_markup=ReplyKeyboardMarkup(
            [["8 класс", "9 класс"], ["10 класс", "11 класс"]],
            resize_keyboard=True, one_time_keyboard=True
        )
    )
    return ASKING_CLASS


async def asking_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["grade"] = update.message.text.strip()
    await update.message.reply_text(
        "Из какого ты города или региона?\n\nПодберу учебные заведения рядом с тобой.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ASKING_REGION


async def asking_region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["region"] = update.message.text.strip()
    await update.message.reply_text(
        "Рассматриваешь платное обучение?",
        reply_markup=ReplyKeyboardMarkup(
            [["Только бюджет", "Готов платить"], ["Рассмотрю оба варианта"]],
            resize_keyboard=True, one_time_keyboard=True
        )
    )
    return ASKING_BUDGET


async def asking_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["budget"] = update.message.text.strip()
    context.user_data["answers"] = []
    context.user_data["question_index"] = 0

    await update.message.reply_text(
        "Поехали! 8 вопросов, отвечай честно — тут нет правильных ответов 🎯",
        reply_markup=ReplyKeyboardMarkup([["А", "Б"], ["В", "Г"]], resize_keyboard=True, one_time_keyboard=True)
    )
    await update.message.reply_text(f"1️⃣ {QUESTIONS[0]}")
    return ASKING_TEST


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    if text not in ["А", "Б", "В", "Г"]:
        await update.message.reply_text("Жми А, Б, В или Г 👇")
        return ASKING_TEST

    context.user_data["answers"].append(text)
    index = context.user_data["question_index"] + 1
    context.user_data["question_index"] = index

    if index < len(QUESTIONS):
        markup = ReplyKeyboardMarkup([["А", "Б"], ["В", "Г"]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(f"{index + 1}️⃣ {QUESTIONS[index]}", reply_markup=markup)
        return ASKING_TEST
    else:
        await update.message.reply_text("Готово, анализирую... ⚡", reply_markup=ReplyKeyboardRemove())
        await analyze_and_respond(update, context)
        return FREE_CHAT


async def analyze_and_respond(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answers = context.user_data["answers"]
    grade = context.user_data.get("grade", "")
    region = context.user_data.get("region", "")
    budget = context.user_data.get("budget", "")

    pairs = [f"Вопрос {i+1}: {q}\nОтвет: {a}" for i, (q, a) in enumerate(zip(QUESTIONS, answers))]
    answers_text = "\n\n".join(pairs)

    prompt = f"""Ты профориентационный эксперт — умный старший друг, не скучный консультант. Отвечай ТОЛЬКО на русском, никаких иностранных символов.

Данные:
- Класс: {grade}
- Регион: {region}  
- Бюджет: {budget}

Ответы на тест:
{answers_text}

Напиши живо и по делу, строго по структуре:

🧠 Твой профиль
2-3 предложения — кто ты по складу характера и что тебя драйвит. Живо, без штампов.

💼 Топ-3 профессии
Для каждой одной строкой: название → почему подходит → средняя зарплата → что сдавать.

🎓 Где учиться в {region}
По 1-2 реальных заведения на каждую профессию. Только те что точно существуют. Учти бюджет: {budget}.

💪 Твои козыри
3 сильные стороны — коротко и конкретно.

🚀 Прямо сейчас
Один конкретный шаг который можно сделать сегодня.

Пиши на "ты", разговорно, как будто объясняешь другу. Никакой воды."""

    try:
        result = ai_request([{"role": "user", "content": prompt}])
        await update.message.reply_text(result)
        await update.message.reply_text(
            "Спрашивай что угодно про профессии — отвечу честно, без прикрас 💬\n\n/start — пройти тест заново"
        )
        context.user_data["profile_summary"] = result
        context.user_data["chat_history"] = []
        increment_tests(update.effective_user.id, grade, region)

        for line in result.split("\n"):
            line = line.strip()
            if line and ("→" in line or line.startswith("•")):
                prof = line.split("→")[0].lstrip("•123. ").strip()
                if 3 < len(prof) < 40:
                    add_profession_stat(prof)
    except Exception as e:
        logger.error(f"AI error: {e}")
        await update.message.reply_text("Что-то сломалось. Попробуй /start заново.")


async def free_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        await update.message.reply_text("Ты заблокирован.")
        return FREE_CHAT

    if not context.user_data.get("profile_summary"):
        await update.message.reply_text("Напиши /start чтобы начать.")
        return FREE_CHAT

    question = update.message.text.strip()
    profile = context.user_data.get("profile_summary", "")
    region = context.user_data.get("region", "")
    budget = context.user_data.get("budget", "")
    history = context.user_data.get("chat_history", [])
    system_prompt = get_system_prompt()

    system = f"""{system_prompt}

Профиль этого человека по результатам теста:
{profile}

Регион: {region} | Бюджет: {budget}"""

    messages = [{"role": "system", "content": system}]
    messages += history[-8:]
    messages.append({"role": "user", "content": question})

    try:
        result = ai_request(messages)
        await update.message.reply_text(result)
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": result})
        context.user_data["chat_history"] = history
        increment_messages(update.effective_user.id)
    except Exception as e:
        logger.error(f"AI error: {e}")
        await update.message.reply_text("Ошибка. Попробуй ещё раз.")

    return FREE_CHAT


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Что умею:\n\n"
        "• Тест профориентации — 8 вопросов\n"
        "• Анализ типа личности\n"
        "• Топ-3 профессии с зарплатой и ЕГЭ\n"
        "• Подборка вузов и колледжей в твоём регионе\n"
        "• Честные ответы на вопросы про профессии\n\n"
        "/start — начать\n"
        "/help — это сообщение"
    )


# ===== АДМИНКА =====

ADMIN_KEYBOARD = ReplyKeyboardMarkup([
    ["📊 Статистика", "👥 Пользователи"],
    ["📢 Рассылка", "🔍 Найти юзера"],
    ["🚫 Забанить", "✅ Разбанить"],
    ["💬 Чат с ИИ", "✏️ Промпт"],
    ["❌ Выйти"]
], resize_keyboard=True)


async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["admin_mode"] = False
    await update.message.reply_text("🔐 Пароль:", reply_markup=ReplyKeyboardRemove())
    return ADMIN_PASSWORD_INPUT


async def admin_check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == ADMIN_PASSWORD:
        context.user_data["admin_mode"] = True
        await show_admin_stats(update)
        return ADMIN_MENU
    await update.message.reply_text("Неверный пароль.")
    return ConversationHandler.END


async def show_admin_stats(update: Update):
    db = load_db()
    users = db["users"]
    total = len(users)
    banned = sum(1 for u in users.values() if u.get("banned"))
    tests = sum(u.get("tests_completed", 0) for u in users.values())
    messages = db.get("total_messages", 0)

    today = datetime.now().date().isoformat()
    active_today = sum(1 for u in users.values() if u.get("last_active", "")[:10] == today)

    top_profs = sorted(db.get("profession_stats", {}).items(), key=lambda x: x[1], reverse=True)[:5]
    top_text = "\n".join([f"  {i+1}. {p} — {c}" for i, (p, c) in enumerate(top_profs)]) if top_profs else "  нет данных"

    top_regions = {}
    for u in users.values():
        r = u.get("region", "")
        if r:
            top_regions[r] = top_regions.get(r, 0) + 1
    top_reg = sorted(top_regions.items(), key=lambda x: x[1], reverse=True)[:3]
    reg_text = ", ".join([f"{r} ({c})" for r, c in top_reg]) if top_reg else "нет данных"

    await update.message.reply_text(
        f"👑 Админ-панель\n\n"
        f"👥 Пользователей: {total}\n"
        f"🟢 Активны сегодня: {active_today}\n"
        f"🚫 Забанено: {banned}\n"
        f"📝 Тестов пройдено: {tests}\n"
        f"💬 Сообщений всего: {messages}\n\n"
        f"🏆 Топ профессий:\n{top_text}\n\n"
        f"📍 Топ регионов: {reg_text}",
        reply_markup=ADMIN_KEYBOARD
    )


async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "❌ Выйти":
        context.user_data["admin_mode"] = False
        await update.message.reply_text("Вышел.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    elif text == "📊 Статистика":
        await show_admin_stats(update)
        return ADMIN_MENU

    elif text == "👥 Пользователи":
        db = load_db()
        users = db["users"]
        if not users:
            await update.message.reply_text("Пользователей нет.")
        else:
            lines = []
            for uid, u in sorted(users.items(), key=lambda x: x[1].get("last_active", ""), reverse=True)[:15]:
                status = "🚫" if u.get("banned") else "🟢"
                name = f"@{u['username']}" if u.get("username") else u.get("first_name", uid)
                grade = u.get("grade", "?")
                region = u.get("region", "?")
                tests = u.get("tests_completed", 0)
                lines.append(f"{status} {name} | {grade} | {region} | тестов: {tests}")
            await update.message.reply_text("Последние 15 пользователей:\n\n" + "\n".join(lines))
        return ADMIN_MENU

    elif text == "📢 Рассылка":
        await update.message.reply_text("Текст рассылки:", reply_markup=ReplyKeyboardRemove())
        return ADMIN_BROADCAST

    elif text == "🔍 Найти юзера":
        await update.message.reply_text("Напиши username или ID:", reply_markup=ReplyKeyboardRemove())
        return ADMIN_USER_INFO

    elif text == "🚫 Забанить":
        await update.message.reply_text("Username или ID для бана:", reply_markup=ReplyKeyboardRemove())
        context.user_data["ban_action"] = "ban"
        return ADMIN_BAN

    elif text == "✅ Разбанить":
        await update.message.reply_text("Username или ID для разбана:", reply_markup=ReplyKeyboardRemove())
        context.user_data["ban_action"] = "unban"
        return ADMIN_BAN

    elif text == "💬 Чат с ИИ":
        await update.message.reply_text(
            "Режим чата с ИИ без ограничений. /adminmenu — вернуться.",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data["admin_chat_history"] = []
        return ADMIN_CHAT

    elif text == "✏️ Промпт":
        current = get_system_prompt()
        await update.message.reply_text(
            f"Текущий промпт:\n\n{current}\n\nНапиши новый:",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADMIN_PROMPT_EDIT

    return ADMIN_MENU


async def admin_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, app):
    text = update.message.text.strip()
    db = load_db()
    users = db["users"]
    sent = 0
    failed = 0

    await update.message.reply_text(f"Отправляю {len(users)} пользователям...")

    for uid, u in users.items():
        if u.get("banned"):
            continue
        try:
            await app.bot.send_message(chat_id=int(uid), text=f"📢 {text}")
            sent += 1
        except Exception:
            failed += 1

    await update.message.reply_text(f"Готово. Отправлено: {sent}, не дошло: {failed}", reply_markup=ADMIN_KEYBOARD)
    return ADMIN_MENU


async def admin_ban_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.text.strip()
    action = context.user_data.get("ban_action", "ban")
    result = ban_user(target, ban=(action == "ban"))

    if result:
        word = "забанен 🚫" if action == "ban" else "разбанен ✅"
        await update.message.reply_text(f"Пользователь {result} {word}.", reply_markup=ADMIN_KEYBOARD)
    else:
        await update.message.reply_text("Пользователь не найден.", reply_markup=ADMIN_KEYBOARD)

    return ADMIN_MENU


async def admin_user_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.text.strip()
    uid, u = get_user_info(target)

    if not u:
        await update.message.reply_text("Не найден.", reply_markup=ADMIN_KEYBOARD)
        return ADMIN_MENU

    status = "🚫 Забанен" if u.get("banned") else "🟢 Активен"
    name = f"@{u['username']}" if u.get("username") else u.get("first_name", "?")
    joined = u.get("joined", "?")[:10]
    last = u.get("last_active", "?")[:10]

    await update.message.reply_text(
        f"👤 {name} (ID: {uid})\n"
        f"Статус: {status}\n"
        f"Класс: {u.get('grade', '?')}\n"
        f"Регион: {u.get('region', '?')}\n"
        f"Тестов: {u.get('tests_completed', 0)}\n"
        f"Сообщений: {u.get('messages_sent', 0)}\n"
        f"Зарегистрирован: {joined}\n"
        f"Последняя активность: {last}",
        reply_markup=ADMIN_KEYBOARD
    )
    return ADMIN_MENU


async def admin_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "/adminmenu":
        await show_admin_stats(update)
        return ADMIN_MENU

    history = context.user_data.get("admin_chat_history", [])
    history.append({"role": "user", "content": text})

    try:
        result = ai_request(history)
        await update.message.reply_text(result)
        history.append({"role": "assistant", "content": result})
        context.user_data["admin_chat_history"] = history[-20:]
    except Exception as e:
        logger.error(f"AI error: {e}")
        await update.message.reply_text("Ошибка.")

    return ADMIN_CHAT


async def admin_prompt_edit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_prompt = update.message.text.strip()
    set_system_prompt(new_prompt)
    await update.message.reply_text("Промпт обновлён ✅", reply_markup=ADMIN_KEYBOARD)
    return ADMIN_MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ===== MAIN =====

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    async def broadcast_wrapper(update, context):
        return await admin_broadcast_handler(update, context, app)

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_PASSWORD_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_check_password)],
            ADMIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler)],
            ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_wrapper)],
            ADMIN_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_ban_handler)],
            ADMIN_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_chat_handler)],
            ADMIN_PROMPT_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_prompt_edit_handler)],
            ADMIN_USER_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_user_info_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    user_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASKING_CLASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, asking_class)],
            ASKING_REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, asking_region)],
            ASKING_BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, asking_budget)],
            ASKING_TEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)],
            FREE_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, free_chat)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(admin_conv)
    app.add_handler(user_conv)
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_chat))
    app.run_polling()


if __name__ == "__main__":
    main()
