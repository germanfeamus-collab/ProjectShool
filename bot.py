import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Состояния
(ASKING_CLASS, ASKING_REGION, ASKING_BUDGET, ASKING_TEST, FREE_CHAT) = range(5)

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


def groq_request(messages):
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": messages
        },
        timeout=60
    )
    return response.json()["choices"][0]["message"]["content"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await update.message.reply_text(
        "👋 Привет! Я помогу тебе разобраться с выбором профессии.\n\n"
        "Сначала несколько вопросов о тебе, потом тест из 8 вопросов — и получишь персональный разбор.\n\n"
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
        "В каком регионе живёшь? Напиши название города или региона.\n\n"
        "Это нужно чтобы подобрать учебные заведения рядом с тобой.",
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
        "Отлично! Теперь тест — 8 вопросов. Отвечай честно, тут нет правильных ответов. 🎯",
        reply_markup=ReplyKeyboardMarkup(
            [["А", "Б"], ["В", "Г"]],
            resize_keyboard=True, one_time_keyboard=True
        )
    )
    await update.message.reply_text(f"1️⃣ {QUESTIONS[0]}")
    return ASKING_TEST


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()

    if text not in ["А", "Б", "В", "Г"]:
        await update.message.reply_text("Выбери один из вариантов: А, Б, В или Г")
        return ASKING_TEST

    context.user_data["answers"].append(text)
    index = context.user_data["question_index"] + 1
    context.user_data["question_index"] = index

    if index < len(QUESTIONS):
        markup = ReplyKeyboardMarkup([["А", "Б"], ["В", "Г"]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(f"{index + 1}️⃣ {QUESTIONS[index]}", reply_markup=markup)
        return ASKING_TEST
    else:
        await update.message.reply_text(
            "⏳ Анализирую твои ответы...",
            reply_markup=ReplyKeyboardRemove()
        )
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

    prompt = f"""Ты профориентационный эксперт для школьников. Отвечай ТОЛЬКО на русском языке.

Данные подростка:
- Класс: {grade}
- Регион: {region}
- Бюджет: {budget}

Ответы на тест:
{answers_text}

Напиши анализ строго по этой структуре, коротко и по делу:

🧠 Твой профиль
2-3 предложения о типе личности и склонностях.

💼 Топ-3 профессии
Для каждой:
• Название
• Почему подходит (1 предложение)
• Средняя зарплата в России
• Что нужно сдавать на ЕГЭ/ОГЭ

🎓 Где учиться в регионе ({region})
Для каждой из 3 профессий — 1-2 реальных учебных заведения (колледж или вуз) с учётом бюджета ({budget}). Пиши только реально существующие заведения.

💪 Сильные стороны
3 качества одной строкой каждое.

🚀 Следующий шаг
Один конкретный совет что сделать прямо сейчас.

Пиши на "ты", без воды."""

    try:
        result = groq_request([{"role": "user", "content": prompt}])
        await update.message.reply_text(result)
        await update.message.reply_text(
            "💬 Задавай любые вопросы про профессии и выбор пути — отвечу честно.\n\n"
            "Например: «а подойдёт ли мне юрист?» или «расскажи про IT»\n\n"
            "Новый тест — /start"
        )
        context.user_data["profile_summary"] = result
        context.user_data["chat_history"] = []
    except Exception as e:
        logger.error(f"Groq error: {e}")
        await update.message.reply_text("Что-то пошло не так. Попробуй /start заново.")


async def free_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("profile_summary"):
        await update.message.reply_text("Напиши /start чтобы начать.")
        return FREE_CHAT

    question = update.message.text.strip()
    profile = context.user_data.get("profile_summary", "")
    region = context.user_data.get("region", "")
    budget = context.user_data.get("budget", "")
    history = context.user_data.get("chat_history", [])

    system = f"""Ты профориентационный эксперт для школьников. Отвечай ТОЛЬКО на русском языке.

Профиль этого подростка:
{profile}

Его регион: {region}
Бюджет на обучение: {budget}

Правила:
- Отвечай только на вопросы про профессии, образование, карьеру и выбор пути
- Если вопрос не по теме — вежливо скажи что ты только про профориентацию
- Будь честным: если профессия не подходит этому человеку по его профилю — скажи прямо и объясни почему
- Если спрашивают про учебные заведения — называй реальные, желательно в его регионе
- Коротко, 3-5 предложений"""

    messages = [{"role": "system", "content": system}]
    messages += history[-6:]  # последние 3 обмена
    messages.append({"role": "user", "content": question})

    try:
        result = groq_request(messages)
        await update.message.reply_text(result)

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": result})
        context.user_data["chat_history"] = history
    except Exception as e:
        logger.error(f"Groq error: {e}")
        await update.message.reply_text("Что-то пошло не так. Попробуй ещё раз.")

    return FREE_CHAT


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Что я умею:\n\n"
        "• Тест профориентации из 8 вопросов\n"
        "• Анализ твоего типа личности\n"
        "• Топ-3 профессии под тебя со средней зарплатой\n"
        "• Подборка вузов и колледжей в твоём регионе\n"
        "• Честные ответы на любые вопросы про профессии\n\n"
        "Команды:\n"
        "/start — начать тест заново\n"
        "/help — это сообщение"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Тест прерван. Напиши /start чтобы начать заново.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
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

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_chat))
    app.run_polling()


if __name__ == "__main__":
    main()
