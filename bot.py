import os
import json
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
DB_FILE = "db.json"

# Состояния обычного бота
(ASKING_CLASS, ASKING_REGION, ASKING_BUDGET, ASKING_TEST, FREE_CHAT) = range(5)
# Состояния админки
(ADMIN_PASSWORD_INPUT, ADMIN_MENU, ADMIN_BROADCAST, ADMIN_BAN, ADMIN_CHAT,
 ADMIN_PROMPT_EDIT) = range(5, 11)

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

DEFAULT_SYSTEM_PROMPT = """Ты профориентационный эксперт для школьников. Отвечай ТОЛЬКО на русском языке.

Правила:
- Отвечай только на вопросы про профессии, образование, карьеру и выбор пути
- Если вопрос не по теме — вежливо скажи что ты только про профориентацию
- Будь честным: если профессия не подходит — скажи прямо и объясни почему
- Называй реальные учебные заведения
- Коротко, 3-5 предложений"""


# ===== БД (простой JSON файл) =====

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "system_prompt": DEFAULT_SYSTEM_PROMPT, "profession_stats": {}}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def register_user(user_id, username):
    db = load_db()
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {
            "username": username,
            "joined": datetime.now().isoformat(),
            "tests_completed": 0,
            "banned": False,
            "last_active": datetime.now().isoformat(),
        }
    else:
        db["users"][uid]["last_active"] = datetime.now().isoformat()
        db["users"][uid]["username"] = username
    save_db(db)

def is_banned(user_id):
    db = load_db()
    uid = str(user_id)
    return db["users"].get(uid, {}).get("banned", False)

def increment_tests(user_id):
    db = load_db()
    uid = str(user_id)
    if uid in db["users"]:
        db["users"][uid]["tests_completed"] = db["users"][uid].get("tests_completed", 0) + 1
    save_db(db)

def add_profession_stat(profession):
    db = load_db()
    db["profession_stats"][profession] = db["profession_stats"].get(profession, 0) + 1
    save_db(db)

def get_system_prompt():
    db = load_db()
    return db.get("system_prompt", DEFAULT_SYSTEM_PROMPT)

def set_system_prompt(prompt):
    db = load_db()
    db["system_prompt"] = prompt
    save_db(db)


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
    register_user(user.id, user.username or user.first_name)

    if is_banned(user.id):
        await update.message.reply_text("Ты заблокирован.")
        return ConversationHandler.END

    context.user_data.clear()

    await update.message.reply_text(
        "👋 Привет! Я помогу разобраться с выбором профессии.\n\n"
        "Несколько вопросов о тебе, потом тест из 8 вопросов — и получишь персональный разбор.\n\n"
        "В каком ты классе?",
        reply_markup=ReplyKeyboardMarkup(
            [["8 класс", "9 класс"], ["10 класс", "11 класс"]],
            resize_keyboard=True, one_time_keyboard=True
        )
    )
    return ASKING_CLASS


async def asking_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["grade"] = update.message.text.strip()
    await update.message.reply_text(
        "В каком городе или регионе живёшь?\n\nЭто нужно чтобы подобрать учебные заведения рядом.",
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
        "Отлично! Теперь тест — 8 вопросов. Отвечай честно. 🎯",
        reply_markup=ReplyKeyboardMarkup([["А", "Б"], ["В", "Г"]], resize_keyboard=True, one_time_keyboard=True)
    )
    await update.message.reply_text(f"1️⃣ {QUESTIONS[0]}")
    return ASKING_TEST


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    if text not in ["А", "Б", "В", "Г"]:
        await update.message.reply_text("Выбери: А, Б, В или Г")
        return ASKING_TEST

    context.user_data["answers"].append(text)
    index = context.user_data["question_index"] + 1
    context.user_data["question_index"] = index

    if index < len(QUESTIONS):
        markup = ReplyKeyboardMarkup([["А", "Б"], ["В", "Г"]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(f"{index + 1}️⃣ {QUESTIONS[index]}", reply_markup=markup)
        return ASKING_TEST
    else:
        await update.message.reply_text("⏳ Анализирую твои ответы...", reply_markup=ReplyKeyboardRemove())
        await analyze_and_respond(update, context)
        return FREE_CHAT


async def analyze_and_respond(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answers = context.user_data["answers"]
    grade = context.user_data.get("grade", "")
    region = context.user_data.get("region", "")
    budget = context.user_data.get("budget", "")

    pairs = []
    for i, (q, a) in enumerate(zip(QUESTIONS, answers)):
        pairs.append(f"Вопрос {i+1}: {q}\nОтвет: {a}")
    answers_text = "\n\n".join(pairs)

    prompt = f"""Ты профориентационный эксперт для школьников. Отвечай ТОЛЬКО на русском языке, никаких иностранных символов.

Данные подростка:
- Класс: {grade}
- Регион: {region}
- Бюджет: {budget}

Ответы на тест:
{answers_text}

Напиши анализ строго по структуре, коротко:

🧠 Твой профиль
2-3 предложения о типе личности.

💼 Топ-3 профессии
Для каждой: название, почему подходит (1 предложение), средняя зарплата, что сдавать на ЕГЭ/ОГЭ.

🎓 Где учиться в {region}
1-2 реальных заведения для каждой профессии с учётом бюджета ({budget}).

💪 Сильные стороны
3 качества.

🚀 Следующий шаг
Один конкретный совет.

Пиши на "ты", без воды."""

    try:
        result = ai_request([{"role": "user", "content": prompt}])
        await update.message.reply_text(result)
        await update.message.reply_text(
            "💬 Задавай любые вопросы про профессии — отвечу честно.\n/start — новый тест"
        )
        context.user_data["profile_summary"] = result
        context.user_data["chat_history"] = []
        increment_tests(update.effective_user.id)

        # парсим профессии для статистики (грубо)
        for line in result.split("\n"):
            if line.startswith("•") or (len(line) > 2 and line[0].isdigit() and line[1] == "."):
                prof = line.lstrip("•1234567890. ").split("—")[0].strip()
                if prof:
                    add_profession_stat(prof)
    except Exception as e:
        logger.error(f"AI error: {e}")
        await update.message.reply_text("Что-то пошло не так. Попробуй /start заново.")


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

Профиль подростка:
{profile}

Регион: {region}
Бюджет: {budget}"""

    messages = [{"role": "system", "content": system}]
    messages += history[-6:]
    messages.append({"role": "user", "content": question})

    try:
        result = ai_request(messages)
        await update.message.reply_text(result)
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": result})
        context.user_data["chat_history"] = history
    except Exception as e:
        logger.error(f"AI error: {e}")
        await update.message.reply_text("Что-то пошло не так. Попробуй ещё раз.")

    return FREE_CHAT


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Что я умею:\n\n"
        "• Тест профориентации из 8 вопросов\n"
        "• Анализ типа личности\n"
        "• Топ-3 профессии со средней зарплатой\n"
        "• Подборка вузов и колледжей в твоём регионе\n"
        "• Честные ответы на вопросы про профессии\n\n"
        "/start — начать тест\n"
        "/help — это сообщение\n"
        "/admin — панель управления"
    )


# ===== АДМИНКА =====

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["admin_mode"] = False
    await update.message.reply_text(
        "🔐 Введи пароль администратора:",
        reply_markup=ReplyKeyboardRemove()
    )
    return ADMIN_PASSWORD_INPUT


async def admin_check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == ADMIN_PASSWORD:
        context.user_data["admin_mode"] = True
        await show_admin_menu(update)
        return ADMIN_MENU
    else:
        await update.message.reply_text("Неверный пароль.")
        return ConversationHandler.END


async def show_admin_menu(update: Update):
    db = load_db()
    users = db["users"]
    total = len(users)
    banned = sum(1 for u in users.values() if u.get("banned"))
    tests = sum(u.get("tests_completed", 0) for u in users.values())

    top_profs = sorted(db.get("profession_stats", {}).items(), key=lambda x: x[1], reverse=True)[:5]
    top_text = "\n".join([f"  {p}: {c}" for p, c in top_profs]) if top_profs else "  нет данных"

    await update.message.reply_text(
        f"👑 Панель администратора\n\n"
        f"📊 Статистика:\n"
        f"  Пользователей: {total}\n"
        f"  Забанено: {banned}\n"
        f"  Тестов пройдено: {tests}\n\n"
        f"🏆 Топ профессий:\n{top_text}\n\n"
        f"Выбери действие:",
        reply_markup=ReplyKeyboardMarkup([
            ["📢 Рассылка", "🚫 Забанить"],
            ["✅ Разбанить", "👥 Пользователи"],
            ["💬 Чат с ИИ", "✏️ Изменить промпт"],
            ["❌ Выйти"]
        ], resize_keyboard=True)
    )


async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "❌ Выйти":
        context.user_data["admin_mode"] = False
        await update.message.reply_text("Вышел из админки.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    elif text == "📢 Рассылка":
        await update.message.reply_text("Напиши текст рассылки:", reply_markup=ReplyKeyboardRemove())
        return ADMIN_BROADCAST

    elif text == "🚫 Забанить":
        await update.message.reply_text("Напиши username или ID пользователя:", reply_markup=ReplyKeyboardRemove())
        context.user_data["ban_action"] = "ban"
        return ADMIN_BAN

    elif text == "✅ Разбанить":
        await update.message.reply_text("Напиши username или ID пользователя:", reply_markup=ReplyKeyboardRemove())
        context.user_data["ban_action"] = "unban"
        return ADMIN_BAN

    elif text == "👥 Пользователи":
        db = load_db()
        users = db["users"]
        if not users:
            await update.message.reply_text("Пользователей нет.")
        else:
            lines = []
            for uid, u in list(users.items())[-20:]:
                status = "🚫" if u.get("banned") else "✅"
                lines.append(f"{status} @{u.get('username', uid)} | тестов: {u.get('tests_completed', 0)}")
            await update.message.reply_text("Последние 20 пользователей:\n\n" + "\n".join(lines))
        await show_admin_menu(update)
        return ADMIN_MENU

    elif text == "💬 Чат с ИИ":
        await update.message.reply_text(
            "Режим чата с ИИ без ограничений. Пиши что угодно.\n/adminmenu — вернуться в меню",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data["admin_chat_history"] = []
        return ADMIN_CHAT

    elif text == "✏️ Изменить промпт":
        current = get_system_prompt()
        await update.message.reply_text(
            f"Текущий системный промпт:\n\n{current}\n\nНапиши новый промпт:",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADMIN_PROMPT_EDIT

    return ADMIN_MENU


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, app):
    text = update.message.text.strip()
    db = load_db()
    users = db["users"]
    sent = 0
    failed = 0

    await update.message.reply_text(f"Отправляю {len(users)} пользователям...")

    for uid in users:
        if users[uid].get("banned"):
            continue
        try:
            await app.bot.send_message(chat_id=int(uid), text=f"📢 Сообщение от администратора:\n\n{text}")
            sent += 1
        except Exception:
            failed += 1

    await update.message.reply_text(f"Готово. Отправлено: {sent}, не доставлено: {failed}")
    await show_admin_menu(update)
    return ADMIN_MENU


async def admin_ban_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.text.strip().lstrip("@")
    action = context.user_data.get("ban_action", "ban")
    db = load_db()

    found = False
    for uid, u in db["users"].items():
        if u.get("username") == target or uid == target:
            db["users"][uid]["banned"] = (action == "ban")
            found = True
            break

    if found:
        save_db(db)
        word = "забанен" if action == "ban" else "разбанен"
        await update.message.reply_text(f"Пользователь @{target} {word}.")
    else:
        await update.message.reply_text("Пользователь не найден.")

    await show_admin_menu(update)
    return ADMIN_MENU


async def admin_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "/adminmenu":
        await show_admin_menu(update)
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
        await update.message.reply_text("Ошибка. Попробуй ещё раз.")

    return ADMIN_CHAT


async def admin_prompt_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_prompt = update.message.text.strip()
    set_system_prompt(new_prompt)
    await update.message.reply_text("Промпт обновлён.")
    await show_admin_menu(update)
    return ADMIN_MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ===== MAIN =====

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Обычный бот
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

    # Рассылка с доступом к app
    async def broadcast_wrapper(update, context):
        return await admin_broadcast(update, context, app)

    # Админка
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_PASSWORD_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_check_password)],
            ADMIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler)],
            ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_wrapper)],
            ADMIN_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_ban_handler)],
            ADMIN_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_chat_handler)],
            ADMIN_PROMPT_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_prompt_edit)],
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
