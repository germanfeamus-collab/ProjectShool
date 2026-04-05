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
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

QUESTIONS = [
    "1️⃣ Что тебе больше нравится?\n\nА) Работать с людьми\nБ) Работать с техникой/компьютерами\nВ) Работать с природой/животными\nГ) Работать с текстами/творчеством",
    "2️⃣ Как ты проводишь свободное время?\n\nА) Общаюсь с друзьями, организую мероприятия\nБ) Играю в игры, программирую, собираю что-то\nВ) Провожу время на природе, занимаюсь спортом\nГ) Рисую, пишу, слушаю музыку",
    "3️⃣ Какой предмет в школе даётся легче всего?\n\nА) История, обществознание, литература\nБ) Математика, физика, информатика\nВ) Биология, химия, география\nГ) Русский язык, ИЗО, музыка",
    "4️⃣ Каким ты видишь себя через 10 лет?\n\nА) Помогаю людям, работаю в команде\nБ) Создаю технологии, решаю сложные задачи\nВ) Работаю на свежем воздухе, занимаюсь исследованиями\nГ) Занимаюсь творчеством, создаю что-то уникальное",
    "5️⃣ Что для тебя важнее в работе?\n\nА) Общение и помощь другим\nБ) Логика и точность\nВ) Физическая активность и природа\nГ) Свобода и самовыражение",
    "6️⃣ Как ты принимаешь решения?\n\nА) Советуюсь с другими, учитываю чувства людей\nБ) Анализирую факты и логически размышляю\nВ) Доверяю интуиции и практическому опыту\nГ) Слушаю своё сердце и творческий импульс",
    "7️⃣ Какой тип задач тебе нравится?\n\nА) Организовывать людей и процессы\nБ) Решать технические и математические задачи\nВ) Исследовать и экспериментировать\nГ) Создавать и придумывать новое",
    "8️⃣ Что тебя больше всего раздражает?\n\nА) Когда люди не могут договориться\nБ) Когда что-то работает неправильно и непонятно почему\nВ) Когда приходится сидеть в офисе весь день\nГ) Когда нет места для творчества и инициативы",
]

ASKING = range(1)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["answers"] = []
    context.user_data["question_index"] = 0

    await update.message.reply_text(
        "👋 Привет! Я твой навигатор в мире профессий.\n\n"
        "Отвечу на главный вопрос — кем тебе стать.\n\n"
        "Задам 8 вопросов, потом ИИ проанализирует твои ответы и даст персональные рекомендации.\n\n"
        "Поехали! 🚀",
        reply_markup=ReplyKeyboardRemove()
    )

    keyboard = [["А", "Б"], ["В", "Г"]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(QUESTIONS[0], reply_markup=markup)
    return ASKING


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()

    if text not in ["А", "Б", "В", "Г"]:
        await update.message.reply_text("Выбери один из вариантов: А, Б, В или Г")
        return ASKING

    context.user_data["answers"].append(text)
    index = context.user_data["question_index"] + 1
    context.user_data["question_index"] = index

    if index < len(QUESTIONS):
        keyboard = [["А", "Б"], ["В", "Г"]]
        markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(QUESTIONS[index], reply_markup=markup)
        return ASKING
    else:
        await update.message.reply_text(
            "⏳ Анализирую твои ответы... Это займёт несколько секунд.",
            reply_markup=ReplyKeyboardRemove()
        )
        await analyze_and_respond(update, context)
        return ConversationHandler.END


async def analyze_and_respond(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answers = context.user_data["answers"]

    pairs = []
    for i, (q, a) in enumerate(zip(QUESTIONS, answers)):
        pairs.append(f"Вопрос {i+1}:\n{q}\nОтвет пользователя: {a}")

    answers_text = "\n\n".join(pairs)

    prompt = f"""Ты профориентационный эксперт для школьников 8–10 классов.

Проанализируй ответы подростка на тест профориентации и дай персональные рекомендации.

Ответы на тест:
{answers_text}

Напиши структурированный анализ:

1. Твой профиль — опиши тип личности и склонности (3–4 предложения)
2. Топ-3 профессии для тебя — для каждой: название, почему подходит, что нужно изучать
3. Твои сильные стороны — что выделяет этого человека
4. Следующий шаг — конкретный совет что сделать прямо сейчас

Пиши тепло, на "ты", без занудства. Подросток должен почувствовать что его поняли."""

    try:
        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "mistral-large-latest",
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        result = response.json()["choices"][0]["message"]["content"]
        await update.message.reply_text(result)
        await update.message.reply_text("🔄 Хочешь пройти тест заново? Напиши /start")
    except Exception as e:
        logger.error(f"Mistral error: {e}")
        await update.message.reply_text(
            "Что-то пошло не так при анализе. Попробуй /start заново."
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
            ASKING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.run_polling()


if __name__ == "__main__":
    main()
