import sqlite3
import logging
from typing import Optional

from telegram import Update, ChatMemberUpdated, User
from telegram.constants import ParseMode   # <-- to'g'ri joydan import
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    ChatMemberHandler,
)

# --- CONFIG ---
TOKEN = "8584405557:AAHn04FShJlOjTxr9qIuOK0X0nRvIYoIQiQ"
DB_PATH = "invites.db"
# --------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS invites (
        group_id INTEGER,
        inviter_id INTEGER,
        inviter_username TEXT,
        inviter_fullname TEXT,
        count INTEGER,
        PRIMARY KEY (group_id, inviter_id)
    )
    """)
    conn.commit()
    conn.close()

def add_invite(group_id: int, inviter: User):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO invites (group_id, inviter_id, inviter_username, inviter_fullname, count)
    VALUES (?, ?, ?, ?, 1)
    ON CONFLICT(group_id, inviter_id) DO UPDATE SET
      inviter_username=excluded.inviter_username,
      inviter_fullname=excluded.inviter_fullname,
      count = invites.count + 1
    """, (
        group_id,
        inviter.id,
        inviter.username,
        inviter.full_name
    ))
    conn.commit()
    conn.close()

def get_top_invites(group_id: int, limit: int = 100):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    SELECT inviter_id, inviter_username, inviter_fullname, count
    FROM invites
    WHERE group_id = ?
    ORDER BY count DESC
    LIMIT ?
    """, (group_id, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data: ChatMemberUpdated = update.chat_member
    if not data.new_chat_member or not data.new_chat_member.user:
        return

    new_user = data.new_chat_member.user
    inviter = data.from_user
    chat = data.chat

    if data.old_chat_member.status == "left" and data.new_chat_member.status in ("member", "administrator"):
        if inviter and inviter.id != new_user.id:
            add_invite(chat.id, inviter)
            logger.info(f"{inviter.full_name} {new_user.full_name} ni qo‘shdi")

async def odam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return

    top = get_top_invites(chat.id, limit=100)

    if not top:
        await update.message.reply_text("Hozircha hech kim odam qo‘shmagan.")
        return

    text = "🔝 <b>Guruh TOP 100 (eng ko‘p odam qo‘shganlar):</b>\n\n"
    for i, (uid, uname, fname, cnt) in enumerate(top, start=1):
        if uname:
            profile_link = f"<a href='https://t.me/{uname}'>@{uname}</a>"
        else:
            safe_name = fname or "Noma’lum foydalanuvchi"
            profile_link = f"<a href='tg://user?id={uid}'>{safe_name}</a>"

        text += f"{i}. {profile_link} — {cnt} ta\n"

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CommandHandler("odam", odam_command))

    print("Bot ishga tushdi...")
    app.run_polling(allowed_updates=["chat_member", "message"])

if __name__ == "__main__":
    main()
