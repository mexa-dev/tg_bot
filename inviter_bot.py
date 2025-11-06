import sqlite3
import logging
from typing import List, Optional

from telegram import Update, User
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

# --- CONFIG ---
TOKEN = "8584405557:AAHn04FShJlOjTxr9qIuOK0X0nRvIYoIQiQ"  # BotFather dan olgan tokenni shu yerga qo'ying.
DB_PATH = "invites.db"
# ----------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Database helper ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # jadval: group_id, inviter_id, inviter_username, count
    cur.execute("""
    CREATE TABLE IF NOT EXISTS invites (
        group_id INTEGER,
        inviter_id INTEGER,
        inviter_username TEXT,
        count INTEGER,
        PRIMARY KEY (group_id, inviter_id)
    )
    """)
    conn.commit()
    conn.close()

def add_invite(group_id: int, inviter: User, n: int = 1):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Eslatma: ? lar soni va tuple uzunligi mos bo'lishi kerak (5 ta ? -> 5 ta qiymat)
    cur.execute("""
    INSERT INTO invites (group_id, inviter_id, inviter_username, count)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(group_id, inviter_id) DO UPDATE SET
      inviter_username=excluded.inviter_username,
      count = invites.count + ?
    """, (group_id, inviter.id, inviter.username or f"{inviter.first_name}", n, n))
    conn.commit()
    conn.close()

def get_top_invites(group_id: int, limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    SELECT inviter_id, inviter_username, count
    FROM invites
    WHERE group_id = ?
    ORDER BY count DESC
    LIMIT ?
    """, (group_id, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_user_count(group_id: int, user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    SELECT count FROM invites WHERE group_id = ? AND inviter_id = ?
    """, (group_id, user_id))
    r = cur.fetchone()
    conn.close()
    return r[0] if r else 0

def get_user_count_by_username(group_id: int, username: str) -> Optional[int]:
    """
    username - @ bilan yoki yo'q bo'lgan holatlarni qo'llaydi.
    Qidiruv inviter_username bilan LIKE qilingan holda amalga oshiriladi.
    """
    if username.startswith("@"):
        username = username[1:]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # exact match first
    cur.execute("SELECT count FROM invites WHERE group_id = ? AND inviter_username = ?", (group_id, username))
    r = cur.fetchone()
    if r:
        conn.close()
        return r[0]
    # agar exact yo'q bo'lsa, LIKE qidiruvi (ism bo'yicha)
    cur.execute("SELECT count FROM invites WHERE group_id = ? AND inviter_username LIKE ?", (group_id, f"%{username}%"))
    r2 = cur.fetchone()
    conn.close()
    return r2[0] if r2 else None

def reset_group(group_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM invites WHERE group_id = ?", (group_id,))
    conn.commit()
    conn.close()

# --- Handlers ---
async def new_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    new_members: List[User] = msg.new_chat_members or []
    if not new_members:
        return

    chat = update.effective_chat
    inviter = msg.from_user

    count_new = len(new_members)
    try:
        add_invite(chat.id, inviter, count_new)
        logger.info("Group %s: %s added %d members", chat.title or chat.id, inviter.id, count_new)
    except Exception as e:
        logger.exception("DB error: %s", e)

async def odam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /odam
    /odam @username
    - agar arg yo'q bo'lsa -> yuborgan foydalanuvchining soni va TOP10 ni ko'rsatadi
    - agar @username bo'lsa -> o'sha foydalanuvchining sonini ko'rsatadi
    """
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return

    args = context.args or []

    if len(args) >= 1:
        # foydalanuvchi nomi yoki id bilan so'rov
        target = args[0]
        # agar raqam bo'lsa, id deb qabul qilamiz
        if target.lstrip("-").isdigit():
            target_id = int(target)
            cnt = get_user_count(chat.id, target_id)
            await update.message.reply_text(f"Foydalanuvchi (id: {target_id}) bu guruhga {cnt} ta odam qo'shgansiz.")
            return
        else:
            cnt = get_user_count_by_username(chat.id, target)
            if cnt is None:
                await update.message.reply_text(f"{target} uchun ma'lumot topilmadi.")
            else:
                await update.message.reply_text(f"{target} bu guruhga {cnt} ta odam qo'shgan.")
            return

    # agar argument bo'lmasa -> yuborgan foydalanuvchining natijasi + TOP10
    my_cnt = get_user_count(chat.id, user.id)
    top = get_top_invites(chat.id, limit=10)

    lines = []
    # Avval o'zingizning hisobingiz
    display_name = user.username and f"@{user.username}" or f"{user.full_name}"
    # TOP10
    if not top:
        lines.append("Hozircha guruhda saqlangan qo'shishlar yo'q.")
    else:
        lines.append("🔝 Guruh TOP10 (eng ko'p qo'shganlar):")
        for i, (uid, uname, cnt) in enumerate(top, start=1):
            # imkoniyat bo'lsa, foydalanuvchini @username bilan ko'rsatish, aks holda uid
            if uname:
                name = f"@{uname}" if not uname.startswith("@") else uname
            else:
                name = f"id:{uid}"
            lines.append(f"{i}. {name} — {cnt} ta")

    text = "\n".join(lines)
    # HTML parse mode bilan yuborish (qalin qilish uchun <b> ishlatdik)
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

# eski buyruqlar ham saqlanadi (leaderboard, mycount, reset, stats)
async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return
    rows = get_top_invites(chat.id)
    if not rows:
        await update.message.reply_text("Hozircha kimnidir qo'shganlar haqida ma'lumot yo'q.")
        return

    text_lines = ["🔝 Guruhdagi eng ko‘p odam qo‘shganlar:"]
    for i, (uid, uname, cnt) in enumerate(rows, start=1):
        display = f"@{uname}" if uname and not uname.startswith("@") else (uname or str(uid))
        text_lines.append(f"{i}. {display} — {cnt} ta")
    await update.message.reply_text("\n".join(text_lines))

async def mycount_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return
    cnt = get_user_count(chat.id, user.id)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return
    member = await chat.get_member(user.id)
    if not (member.status in ("administrator", "creator")):
        await update.message.reply_text("Bu buyruqni faqat guruh adminlari ishlatishi mumkin.")
        return

    reset_group(chat.id)
    await update.message.reply_text("Guruh bo'yicha barcha saqlangan qo'shishlar o'chirildi.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return
    rows = get_top_invites(chat.id, limit=50)
    total = sum(r[2] for r in rows)
    await update.message.reply_text(f"Guruh bo'yicha jami saqlangan qo'shishlar: {total} ta.")

# --- Main ---
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_members_handler))
    app.add_handler(CommandHandler("odam", odam_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("mycount", mycount_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("stats", stats_command))

    print("Bot ishga tushdi...")
    app.run_polling(allowed_updates=["message", "chat_member"])

if __name__ == "__main__":
    main()