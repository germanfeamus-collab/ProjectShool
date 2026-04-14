import os
import json
import logging
import time
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

if not TELEGRAM_TOKEN:
    raise ValueError("Нет TELEGRAM_TOKEN")

if not OPENROUTER_API_KEY:
    raise ValueError("Нет OPENROUTER_API_KEY")

LAST_MESSAGE_TIME = {}

# ===== БД =====

def load_db():
    if not os.path.exists(DB_FILE):
        db = {
            "users": {},
            "system_prompt": "",
            "profession_stats": {},
            "total_messages": 0,
            "admin_ids": []
        }
        save_db(db)
        return db
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

# ===== ФИКС AI =====

def ai_request(messages):
    try:
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

        data = response.json()

        if "choices" not in data:
            logger.error(f"OpenRouter error: {data}")
            return "Ошибка ИИ. Попробуй позже."

        return data["choices"][0]["message"]["content"]

    except Exception as e:
        logger.error(f"Request failed: {e}")
        return "Ошибка запроса к ИИ."

# ===== УТИЛИТЫ =====

def is_spam(user_id):
    now = time.time()
    if user_id in LAST_MESSAGE_TIME and now - LAST_MESSAGE_TIME[user_id] < 1:
        return True
    LAST_MESSAGE_TIME[user_id] = now
    return False

# ===== БОТ =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот запущен. Напиши что-нибудь.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start /help /stats")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    await update.message.reply_text(
        f"Юзеров: {len(db['users'])}\nСообщений: {db['total_messages']}"
    )

async def free_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if is_spam(user_id):
        return

    text = update.message.text.strip()
    if not text:
        return

    db = load_db()
    uid = str(user_id)

    if uid not in db["users"]:
        db["users"][uid] = {"messages": 0}

    db["users"][uid]["messages"] += 1
    db["total_messages"] += 1
    save_db(db)

    result = ai_request([
        {"role": "user", "content": text}
    ])

    await update.message.reply_text(result)

# ===== АДМИН =====

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in load_db()["admin_ids"]:
        return

    text = " ".join(context.args)
    db = load_db()

    for uid in db["users"]:
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
        except:
            pass

    await update.message.reply_text("Рассылка отправлена")

# ===== MAIN =====

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_chat))

    app.run_polling()

if __name__ == "__main__":
    main()
